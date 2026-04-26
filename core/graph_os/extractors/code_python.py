"""graph_os — Python extractor (I.4).

PURPOSE:  Turn a single Python module into GraphNodes + GraphEdges —
          imports, classes, methods, calls, decorators — using the
          standard-library `ast` parser as the deterministic baseline.
          The tree-sitter + LSP overlays in I.5 and I.7 raise
          confidence for edges this pass can only guess at.
INPUT:    module path + raw source text.
OUTPUT:   ExtractionResult (same shape as md_links / task_deps).
DEPENDS:  Python's stdlib `ast`; no tree-sitter / LSP.
NOTES:    This module deliberately does NOT require tree-sitter —
          builds CI stays green on machines that cannot install the
          grammar. The tree-sitter adapter lives in a sibling module
          (`code_python_ts.py`, ships in I.4b) and agrees with this
          baseline on deterministic fixtures. See plan Section 7
          (7-step lookup) for the resolution ladder; this extractor
          implements the pure-Python subset (steps 1-3) and marks
          everything else as `unresolved` so the LSP overlay can fix
          them later.
"""

from __future__ import annotations

import ast
import hashlib
import logging
from dataclasses import dataclass
from pathlib import PurePosixPath

from ..types import EvidenceSignal, GraphEdge, GraphNode
from .md_links import (
    ExtractionResult,
    ParseError,
    _normalize_path,
    _promote_stubs,
    emit_contains_spine,
)

logger = logging.getLogger("graph_os.extractors.code_python")

EXTRACTOR_ID = "code_python@v1"
# TASK-119: separate ID for the tree-sitter-primary import path so
# provenance_for() can distinguish ast-emitted edges from
# tree-sitter-emitted ones.
EXTRACTOR_ID_TS_IMPORTS = "code_python_ts@v1"


def _tree_sitter_imports_active() -> bool:
    """True when imports should be parsed via tree-sitter.

    Activation conditions:
      - tree-sitter-python grammar is loadable, AND
      - COS_EXTRACTOR_PREFERENCE is "tree-sitter" (default `auto`
        keeps the legacy ast path so existing graphs don't double-emit
        edges with two different extractor tags during rollout).
    """
    import os as _os

    pref = (_os.environ.get("COS_EXTRACTOR_PREFERENCE") or "auto").lower()
    if pref != "tree-sitter":
        return False
    try:
        from ..tree_sitter_overlay import _load_language

        return _load_language("python") is not None
    except Exception:  # noqa: BLE001
        return False


def _imports_via_tree_sitter(content: str) -> list[_ImportDecl] | None:
    """Parse Python imports via tree-sitter.

    PURPOSE:    Equivalent of ``visit_Import`` / ``visit_ImportFrom`` for
                the tree-sitter primary path (TASK-119 / TASK-080a).
                Returns the same `_ImportDecl` shape as the ast visitor
                so the emission code is unchanged.
    OUTPUT:     ``list[_ImportDecl]`` ordered by source line, or ``None``
                when the grammar cannot parse the content.

    Notes:
      - Aliases are honoured: `from pkg.sub import Foo as F` keeps
        `imported="Foo"` and `local_name="F"`.
      - Wildcards (`from pkg import *`) emit a single `_ImportDecl`
        with `is_wildcard=True`.
      - Relative imports (`from . import X` / `from ..pkg import Y`)
        prepend the dot count to source_module to match ast semantics.
    """
    try:
        from ..tree_sitter_overlay import parse, node_text
    except ImportError:
        return None

    parsed = parse("python", content)
    if parsed is None:
        return None

    out: list[_ImportDecl] = []
    content_bytes = content.encode("utf-8")

    def _walk(node):
        # Pre-order walk; we only act on import_statement /
        # import_from_statement nodes — siblings recurse via children.
        kind = getattr(node, "type", None)
        if kind == "import_statement":
            _emit_import_statement(node, content_bytes, out)
            return
        if kind == "import_from_statement":
            _emit_import_from(node, content_bytes, out)
            return
        for child in node.children:
            _walk(child)

    _walk(parsed.root)
    out.sort(key=lambda d: d.line)
    return out


def _emit_import_statement(node, content_bytes: bytes, out: list[_ImportDecl]) -> None:
    """Handle `import X` / `import X as Y` / `import X, Y`."""
    # The tree-sitter Python grammar exposes each imported alias as a
    # `dotted_name` (or `aliased_import` when `as` is present) child.
    line = (node.start_point[0] if hasattr(node, "start_point") else 0) + 1
    for child in node.children:
        ctype = getattr(child, "type", None)
        if ctype == "dotted_name":
            name = _node_text(child, content_bytes)
            out.append(
                _ImportDecl(
                    source_module=None,
                    imported=name,
                    local_name=name.split(".")[0],
                    line=line,
                )
            )
        elif ctype == "aliased_import":
            name_node = child.child_by_field_name("name")
            alias_node = child.child_by_field_name("alias")
            if name_node is None or alias_node is None:
                continue
            name = _node_text(name_node, content_bytes)
            alias = _node_text(alias_node, content_bytes)
            out.append(
                _ImportDecl(
                    source_module=None,
                    imported=name,
                    local_name=alias,
                    line=line,
                )
            )


def _emit_import_from(node, content_bytes: bytes, out: list[_ImportDecl]) -> None:
    """Handle `from X import Y as Z`, `from . import X`, `from X import *`."""
    line = (node.start_point[0] if hasattr(node, "start_point") else 0) + 1
    module_node = node.child_by_field_name("module_name")
    name_nodes = list(node.children_by_field_name("name") or [])

    # Tree-sitter's grammar represents `from . import x` with a
    # `relative_import` or a series of `import_prefix` children for
    # the dots; rebuild the leading-dot count from the source text.
    module_text = ""
    if module_node is not None:
        module_text = _node_text(module_node, content_bytes)
    else:
        for child in node.children:
            if getattr(child, "type", None) == "relative_import":
                module_text = _node_text(child, content_bytes)
                break

    # Wildcard import: the body is a `*` token, no aliased_import children.
    is_wildcard = any(
        getattr(c, "type", None) == "wildcard_import"
        or (
            getattr(c, "type", None) == "*"
            and getattr(c, "is_named", True) is False
        )
        for c in node.children
    )
    if is_wildcard:
        out.append(
            _ImportDecl(
                source_module=module_text,
                imported="*",
                local_name="*",
                line=line,
                is_wildcard=True,
            )
        )
        return

    if not name_nodes:
        # Older grammars expose the imported names as `dotted_name` /
        # `aliased_import` children of the `import_from_statement`.
        name_nodes = [
            c
            for c in node.children
            if getattr(c, "type", None) in ("dotted_name", "aliased_import")
        ]

    for name_node in name_nodes:
        ntype = getattr(name_node, "type", None)
        if ntype == "aliased_import":
            inner_name = name_node.child_by_field_name("name")
            inner_alias = name_node.child_by_field_name("alias")
            if inner_name is None or inner_alias is None:
                continue
            imported = _node_text(inner_name, content_bytes)
            local = _node_text(inner_alias, content_bytes)
        elif ntype == "dotted_name":
            imported = _node_text(name_node, content_bytes)
            local = imported
        else:
            continue
        out.append(
            _ImportDecl(
                source_module=module_text,
                imported=imported,
                local_name=local,
                line=line,
            )
        )


def _node_text(node, content_bytes: bytes) -> str:
    try:
        return content_bytes[node.start_byte:node.end_byte].decode(
            "utf-8", errors="replace"
        )
    except Exception:  # noqa: BLE001
        return ""


# ---------------------------------------------------------------------------
# TASK-120 — tree-sitter primary path for class heritage + decorators
# ---------------------------------------------------------------------------


def _tree_sitter_heritage_active() -> bool:
    """True when class heritage and decorator edges should be parsed via
    tree-sitter.  Same activation rule as `_tree_sitter_imports_active`
    so a single ``--extractor=tree-sitter`` flag flips both paths in
    lock-step (TASK-119 + TASK-120)."""
    return _tree_sitter_imports_active()


def _heritage_via_tree_sitter(
    path: str,
    content: str,
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]] | None:
    """Walk the tree-sitter Python AST and return ``(inherits, decorators)``.

    PURPOSE:    Equivalent of `_PythonVisitor.inherits` and
                `decorators_edges` for the tree-sitter primary path.
                Returns the same `(uid, dotted_name)` tuple shape so
                the emission code is unchanged — only the per-edge
                ``extractor`` tag changes when this path is active.
    OUTPUT:     ``(inherits, decorators_edges)`` or ``None`` when the
                grammar can't parse the content.

    Notes:
      - Qualnames mirror the ast visitor (nested classes nest, nested
        functions still emit at module level for the ast path → we
        match that to keep edge counts identical).
      - Decorators are captured for both functions and classes.
      - Self / parent decorator chains preserve their dotted form
        (`a.b.c`) via tree-sitter's `attribute` node textual extent.
    """
    try:
        from ..tree_sitter_overlay import parse
    except ImportError:
        return None

    parsed = parse("python", content)
    if parsed is None:
        return None

    content_bytes = content.encode("utf-8")
    inherits: list[tuple[str, str]] = []
    decorators_edges: list[tuple[str, str]] = []

    def _walk(node, qual_stack: list[str], scope_uid: str | None) -> None:
        ntype = getattr(node, "type", None)
        if ntype == "class_definition":
            name_node = node.child_by_field_name("name")
            if name_node is None:
                return
            class_name = _node_text(name_node, content_bytes)
            new_qual = qual_stack + [class_name]
            class_qualname = ".".join(new_qual)
            class_uid_ = class_uid(path, class_qualname)

            # Bases — `superclasses` field carries an `argument_list`.
            superclasses = node.child_by_field_name("superclasses")
            if superclasses is not None:
                for child in superclasses.children:
                    if getattr(child, "type", None) in (
                        "identifier", "attribute",
                    ):
                        base_name = _node_text(child, content_bytes)
                        if base_name:
                            inherits.append((class_uid_, base_name))

            # Decorators — sibling `decorator` nodes that precede this
            # class_definition inside a `decorated_definition` parent.
            for dec_name in _decorator_names(node, content_bytes):
                decorators_edges.append((class_uid_, dec_name))

            body = node.child_by_field_name("body")
            if body is not None:
                for child in body.children:
                    _walk(child, new_qual, class_uid_)
            return

        if ntype in ("function_definition", "async_function_definition"):
            name_node = node.child_by_field_name("name")
            if name_node is None:
                return
            fn_name = _node_text(name_node, content_bytes)
            new_qual = qual_stack + [fn_name]
            qualname = ".".join(new_qual)
            in_class = (
                scope_uid is not None and scope_uid.startswith("code:class:")
            )
            uid = method_uid(path, qualname) if in_class else function_uid(
                path, qualname,
            )

            for dec_name in _decorator_names(node, content_bytes):
                decorators_edges.append((uid, dec_name))

            body = node.child_by_field_name("body")
            if body is not None:
                for child in body.children:
                    _walk(child, new_qual, uid)
            return

        if ntype == "decorated_definition":
            # Recurse into the wrapped definition; the `_decorator_names`
            # helper handles the decorators attached to that definition.
            for child in node.children:
                _walk(child, qual_stack, scope_uid)
            return

        # Plain pass-through for module-level / unrelated nodes.
        for child in node.children:
            _walk(child, qual_stack, scope_uid)

    _walk(parsed.root, [], None)
    return inherits, decorators_edges


def _decorator_names(definition_node, content_bytes: bytes) -> list[str]:
    """Return dotted names for every decorator attached to
    ``definition_node`` (a class_definition or function_definition).

    The grammar nests the decorator(s) and the definition under a
    ``decorated_definition`` parent.  We walk parent siblings in
    document order so chained decorators preserve their original
    sequence — matching the ast visitor's iteration of
    ``node.decorator_list``.
    """
    parent = getattr(definition_node, "parent", None)
    if parent is None or getattr(parent, "type", None) != "decorated_definition":
        return []
    out: list[str] = []
    for child in parent.children:
        if child is definition_node:
            break
        if getattr(child, "type", None) == "decorator":
            # decorator → expression child carrying the dotted name.
            for inner in child.children:
                itype = getattr(inner, "type", None)
                if itype in ("identifier", "attribute", "call"):
                    text = _node_text(inner, content_bytes).strip()
                    if not text:
                        continue
                    # `@decorator(args)` → strip the `(...)` to keep the
                    # dotted name only, matching `_dotted_name(ast.Call)`.
                    if "(" in text:
                        text = text.split("(", 1)[0].strip()
                    if text:
                        out.append(text)
                    break
    return out


# ---------------------------------------------------------------------------
# uid helpers
# ---------------------------------------------------------------------------


def file_uid(path: str) -> str:
    return f"code:file:{_normalize_path(path)}"


def module_uid(module_name: str) -> str:
    return f"code:module:{module_name}"


def class_uid(path: str, qualname: str) -> str:
    return f"code:class:{_normalize_path(path)}::{qualname}"


def function_uid(path: str, qualname: str) -> str:
    return f"code:function:{_normalize_path(path)}::{qualname}"


def method_uid(path: str, qualname: str) -> str:
    return f"code:method:{_normalize_path(path)}::{qualname}"


# ---------------------------------------------------------------------------
# Visitor state
# ---------------------------------------------------------------------------


@dataclass
class _SymbolDecl:
    """One declaration discovered during the AST walk."""

    uid: str
    kind: str
    name: str
    qualname: str
    line: int
    end_line: int | None
    signature: str
    docstring: str | None
    decorators: tuple[str, ...]
    parent_uid: str | None
    is_method: bool = False


@dataclass
class _CallSite:
    caller_uid: str
    callee_name: str  # last segment of the dotted expression
    full_expr: str  # dotted form for later chain resolution
    line: int
    is_constructor_like: bool  # `Foo()` where Foo looks capitalised


@dataclass
class _ImportDecl:
    """A single `import X` / `from X import Y` statement."""

    source_module: str | None  # `X` in `from X import Y`
    imported: str  # `Y` (or `X` for plain `import X`)
    local_name: str  # alias if present, else imported
    line: int
    is_wildcard: bool = False


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------


def extract(path: str, content: str) -> ExtractionResult:
    """Parse a `.py` file into nodes + edges.

    PURPOSE:      Per-file write path for the orchestrator. Invoked by
                  `auto-reindex-docs.sh` (and the background indexer in
                  Codex sessions) on every save of a Python file
                  matched by `.coding-os/rag-config.yaml::graph.include`.
    INPUT:        file path (repo-relative preferred; normalised) +
                  raw source.
    OUTPUT:       ExtractionResult with code:file, code:module,
                  code:class, code:function, code:method, code:import
                  nodes plus `contains`, `imports`, `inherits_from`,
                  `is_decorated_by`, `calls` edges.
    DEPENDENCIES: stdlib only.
    NOTES:        SyntaxError is caught; we still emit the file node
                  with a `parse_error` entry so the agent can query
                  "which files failed to parse".
    """
    result = ExtractionResult()
    normalised = _normalize_path(path)
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]

    file_node = GraphNode(
        uid=file_uid(path),
        kind="code:file",
        label=PurePosixPath(normalised).name,
        file_path=normalised,
        lang="py",
        content_hash=content_hash,
        metadata={"extractor": EXTRACTOR_ID},
    )
    result.nodes.append(file_node)

    try:
        tree = ast.parse(content, filename=normalised)
    except SyntaxError as exc:
        result.parse_errors.append(
            ParseError(
                kind="syntax_error",
                detail=f"{exc.msg} at line {exc.lineno}",
                line=exc.lineno,
            )
        )
        emit_contains_spine(
            file_path=path,
            file_uid_=file_node.uid,
            result=result,
            extractor_id=EXTRACTOR_ID,
        )
        _promote_stubs(result)
        return result
    except Exception as exc:  # noqa: BLE001
        result.parse_errors.append(ParseError(kind="fatal", detail=str(exc)))
        emit_contains_spine(
            file_path=path,
            file_uid_=file_node.uid,
            result=result,
            extractor_id=EXTRACTOR_ID,
        )
        _promote_stubs(result)
        return result

    mod_name = _module_name_for_path(normalised)
    mod_node = GraphNode(
        uid=module_uid(mod_name),
        kind="code:module",
        label=mod_name,
        file_path=normalised,
        lang="py",
        metadata={"extractor": EXTRACTOR_ID},
    )
    result.nodes.append(mod_node)
    result.edges.append(
        GraphEdge(
            source_uid=file_node.uid,
            target_uid=mod_node.uid,
            edge_type="contains",
            extractor=EXTRACTOR_ID,
            confidence=1.0,
        )
    )

    visitor = _PythonVisitor(path=normalised, module_name=mod_name, content=content)
    visitor.visit(tree)

    # TASK-119: tree-sitter primary path for imports, opt-in via the
    # `--extractor=tree-sitter` flag (TASK-122).  When active and the
    # grammar parse succeeds, replace the ast-derived import list with
    # the tree-sitter one and tag the emitted edges with
    # `code_python_ts@v1` so `provenance_for(...)` returns
    # `"tree-sitter"`.  When inactive (default) the legacy ast path
    # runs unchanged — zero regression risk for existing graphs.
    import_extractor_id = EXTRACTOR_ID
    if _tree_sitter_imports_active():
        ts_imports = _imports_via_tree_sitter(content)
        if ts_imports is not None:
            visitor.imports = ts_imports
            visitor.imported_local_names = {
                d.local_name: d for d in ts_imports if d.local_name != "*"
            }
            import_extractor_id = EXTRACTOR_ID_TS_IMPORTS

    # TASK-120: tree-sitter primary path for class heritage + decorators.
    # Same activation gate as imports — flips both paths in lock-step.
    heritage_extractor_id = EXTRACTOR_ID
    if _tree_sitter_heritage_active():
        ts_heritage = _heritage_via_tree_sitter(normalised, content)
        if ts_heritage is not None:
            ts_inherits, ts_decorators = ts_heritage
            visitor.inherits = ts_inherits
            visitor.decorators_edges = ts_decorators
            heritage_extractor_id = EXTRACTOR_ID_TS_IMPORTS

    # Emit decls + containment.
    for decl in visitor.decls:
        result.nodes.append(
            GraphNode(
                uid=decl.uid,
                kind=decl.kind,
                label=decl.name,
                file_path=normalised,
                start_line=decl.line,
                end_line=decl.end_line,
                signature=decl.signature,
                lang="py",
                doc_blob=decl.docstring,
                ast_hash=_hash_decl(decl),
                metadata={
                    "qualname": decl.qualname,
                    "decorators": list(decl.decorators),
                    "is_method": decl.is_method,
                    "extractor": EXTRACTOR_ID,
                },
            )
        )
        parent = decl.parent_uid or mod_node.uid
        result.edges.append(
            GraphEdge(
                source_uid=parent,
                target_uid=decl.uid,
                edge_type="contains",
                extractor=EXTRACTOR_ID,
                confidence=1.0,
                source_span=f"{normalised}:{decl.line}",
            )
        )

    # Inheritance.
    inherit_signal = (
        "tree_sitter_base_class"
        if heritage_extractor_id == EXTRACTOR_ID_TS_IMPORTS
        else "ast_base_class"
    )
    for subclass_uid, base_name in visitor.inherits:
        result.edges.append(
            GraphEdge(
                source_uid=subclass_uid,
                target_uid=_resolve_symbol(
                    base_name, path=normalised, visitor=visitor
                ),
                edge_type="inherits_from",
                extractor=heritage_extractor_id,
                confidence=_inherit_confidence(base_name, visitor),
                source_span=f"{normalised}",
                evidence=(EvidenceSignal(inherit_signal, 0.9),),
            )
        )

    # TASK-083: type annotations — has_param_type / returns_type / field_of_type.
    for fn_uid, type_name in visitor.param_types:
        result.edges.append(
            GraphEdge(
                source_uid=fn_uid,
                target_uid=_resolve_symbol(
                    type_name, path=normalised, visitor=visitor
                ),
                edge_type="has_param_type",
                extractor=EXTRACTOR_ID,
                confidence=_annotation_confidence(type_name, visitor),
                source_span=normalised,
                evidence=(EvidenceSignal("ast_annotation", 0.9),),
            )
        )
    for fn_uid, type_name in visitor.return_types:
        result.edges.append(
            GraphEdge(
                source_uid=fn_uid,
                target_uid=_resolve_symbol(
                    type_name, path=normalised, visitor=visitor
                ),
                edge_type="returns_type",
                extractor=EXTRACTOR_ID,
                confidence=_annotation_confidence(type_name, visitor),
                source_span=normalised,
                evidence=(EvidenceSignal("ast_annotation", 0.9),),
            )
        )
    for field_stub, type_name in visitor.field_types:
        result.edges.append(
            GraphEdge(
                source_uid=field_stub,
                target_uid=_resolve_symbol(
                    type_name, path=normalised, visitor=visitor
                ),
                edge_type="field_of_type",
                extractor=EXTRACTOR_ID,
                confidence=_annotation_confidence(type_name, visitor),
                source_span=normalised,
                evidence=(EvidenceSignal("ast_annotation", 0.9),),
            )
        )

    # Decorators — is_decorated_by.
    decorator_signal = (
        "tree_sitter_decorator"
        if heritage_extractor_id == EXTRACTOR_ID_TS_IMPORTS
        else "ast_decorator"
    )
    for decorated_uid, dec_name in visitor.decorators_edges:
        result.edges.append(
            GraphEdge(
                source_uid=decorated_uid,
                target_uid=_resolve_symbol(
                    dec_name, path=normalised, visitor=visitor
                ),
                edge_type="is_decorated_by",
                extractor=heritage_extractor_id,
                confidence=_decorator_confidence(dec_name, visitor),
                evidence=(EvidenceSignal(decorator_signal, 0.9),),
            )
        )

    # Imports.
    for imp in visitor.imports:
        imp_uid = f"code:import:{normalised}::{imp.line}:{imp.local_name}"
        result.nodes.append(
            GraphNode(
                uid=imp_uid,
                kind="code:import",
                label=f"import {imp.local_name}",
                file_path=normalised,
                start_line=imp.line,
                lang="py",
                metadata={
                    "source_module": imp.source_module,
                    "imported": imp.imported,
                    "wildcard": imp.is_wildcard,
                    "extractor": import_extractor_id,
                },
            )
        )
        result.edges.append(
            GraphEdge(
                source_uid=mod_node.uid,
                target_uid=imp_uid,
                edge_type="contains",
                extractor=import_extractor_id,
                confidence=1.0,
            )
        )
        target_mod = imp.source_module or imp.imported
        signal_name = (
            "tree_sitter_import"
            if import_extractor_id == EXTRACTOR_ID_TS_IMPORTS
            else "ast_import"
        )
        result.edges.append(
            GraphEdge(
                source_uid=mod_node.uid,
                target_uid=module_uid(target_mod),
                edge_type="imports",
                extractor=import_extractor_id,
                confidence=0.9,
                source_span=f"{normalised}:{imp.line}",
                evidence=(EvidenceSignal(signal_name, 0.9),),
            )
        )

    # Calls. These are the hardest — the pure-Python baseline uses the
    # 3-step subset of the 7-step lookup (same-scope, enclosing-scope,
    # explicit-import). Unresolved references get confidence 0.3 and an
    # `unresolved_call` evidence signal so the LSP overlay can lift
    # them to 0.95 later without double-writing.
    for call in visitor.calls:
        confidence, evidence, resolved_uid = _resolve_call(
            call, visitor=visitor, path=normalised
        )
        result.edges.append(
            GraphEdge(
                source_uid=call.caller_uid,
                target_uid=resolved_uid,
                edge_type="constructs" if call.is_constructor_like else "calls",
                extractor=EXTRACTOR_ID,
                confidence=confidence,
                source_span=f"{normalised}:{call.line}",
                evidence=evidence,
            )
        )

    # S3: Folder→...→File CONTAINS spine (idempotent via uid).
    emit_contains_spine(
        file_path=path,
        file_uid_=file_node.uid,
        result=result,
        extractor_id=EXTRACTOR_ID,
    )

    # S3: File→Class / File→Function / Class→Method ``contains`` edges.
    # The AST visitor already wires Module→decl and Class→Method; we
    # add File→Class, File→Function, and File→Method(top-level) so the
    # tree-view has a direct spine that bypasses the module node. These
    # are idempotent thanks to the backend's (source,target,edge_type,
    # extractor) uniqueness constraint.
    file_uid_str = file_node.uid
    for decl in visitor.decls:
        if decl.kind == "code:class" and decl.parent_uid is None:
            result.edges.append(
                GraphEdge(
                    source_uid=file_uid_str,
                    target_uid=decl.uid,
                    edge_type="contains",
                    extractor=EXTRACTOR_ID,
                    confidence=1.0,
                )
            )
        elif decl.kind == "code:function" and decl.parent_uid is None:
            result.edges.append(
                GraphEdge(
                    source_uid=file_uid_str,
                    target_uid=decl.uid,
                    edge_type="contains",
                    extractor=EXTRACTOR_ID,
                    confidence=1.0,
                )
            )

    _promote_stubs(result)
    return result


# ---------------------------------------------------------------------------
# AST visitor
# ---------------------------------------------------------------------------


class _PythonVisitor(ast.NodeVisitor):
    """Walk an AST once, collecting decls + imports + calls.

    PURPOSE:      Single-pass depth-first walk that stays fast enough
                  for the sync <200ms incremental budget (plan §8.2).
    NOTES:        Nested functions are tracked but lambdas are only
                  counted when assigned to a name.
    """

    def __init__(self, *, path: str, module_name: str, content: str) -> None:
        self.path = path
        self.module_name = module_name
        self.content = content
        self.decls: list[_SymbolDecl] = []
        self.imports: list[_ImportDecl] = []
        self.inherits: list[tuple[str, str]] = []
        self.decorators_edges: list[tuple[str, str]] = []
        self.calls: list[_CallSite] = []
        # TASK-083: type-annotation edges discovered during the AST walk.
        # `param_types`     : (function_uid, type_name)
        # `return_types`    : (function_uid, type_name)
        # `field_types`     : (field_uid,    type_name) — field_uid is
        #                     the per-class field stub `<class_uid>.<name>`.
        self.param_types: list[tuple[str, str]] = []
        self.return_types: list[tuple[str, str]] = []
        self.field_types: list[tuple[str, str]] = []
        # Scope stack: the uid each new call-site counts as living inside.
        self._scope_uid_stack: list[str] = [module_uid(module_name)]
        # Qualname stack: dotted path for nested classes / functions.
        self._qualname_stack: list[str] = []
        # Name -> uid map for same-scope lookup (step 1 of 7-step lookup).
        self.symbols_by_name: dict[str, str] = {}
        self.imported_local_names: dict[str, _ImportDecl] = {}

    # -- import handling ---------------------------------------------------

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            decl = _ImportDecl(
                source_module=None,
                imported=alias.name,
                local_name=alias.asname or alias.name.split(".")[0],
                line=node.lineno,
            )
            self.imports.append(decl)
            self.imported_local_names[decl.local_name] = decl

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = ("." * (node.level or 0)) + (node.module or "")
        for alias in node.names:
            if alias.name == "*":
                self.imports.append(
                    _ImportDecl(
                        source_module=module,
                        imported="*",
                        local_name="*",
                        line=node.lineno,
                        is_wildcard=True,
                    )
                )
                continue
            decl = _ImportDecl(
                source_module=module,
                imported=alias.name,
                local_name=alias.asname or alias.name,
                line=node.lineno,
            )
            self.imports.append(decl)
            self.imported_local_names[decl.local_name] = decl

    # -- class / function / method ----------------------------------------

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        qualname = self._push_qual(node.name)
        uid = class_uid(self.path, qualname)
        parent_uid = self._scope_uid_stack[-1]
        decl = _SymbolDecl(
            uid=uid,
            kind="code:class",
            name=node.name,
            qualname=qualname,
            line=node.lineno,
            end_line=getattr(node, "end_lineno", None),
            signature=_class_signature(node),
            docstring=ast.get_docstring(node),
            decorators=tuple(_dotted_name(d) for d in node.decorator_list),
            parent_uid=parent_uid if parent_uid != module_uid(self.module_name) else None,
        )
        self.decls.append(decl)
        self.symbols_by_name[node.name] = uid

        for base in node.bases:
            self.inherits.append((uid, _dotted_name(base)))
        for dec in node.decorator_list:
            self.decorators_edges.append((uid, _dotted_name(dec)))

        # TASK-083: scan class body for `name: T` and `name: T = default`.
        for stmt in node.body:
            if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                ann_name = _dotted_name(stmt.annotation)
                if ann_name:
                    field_stub = f"{uid}.{stmt.target.id}"
                    self.field_types.append((field_stub, ann_name))

        self._scope_uid_stack.append(uid)
        try:
            self.generic_visit(node)
        finally:
            self._scope_uid_stack.pop()
            self._pop_qual()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node, is_async=False)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node, is_async=True)

    def _visit_function(self, node: ast.AST, *, is_async: bool) -> None:
        name = node.name  # type: ignore[attr-defined]
        qualname = self._push_qual(name)
        in_class = self._scope_uid_stack[-1].startswith("code:class:")
        if in_class:
            uid = method_uid(self.path, qualname)
            kind = "code:method"
        else:
            uid = function_uid(self.path, qualname)
            kind = "code:function"
        parent_uid = self._scope_uid_stack[-1]
        decl = _SymbolDecl(
            uid=uid,
            kind=kind,
            name=name,
            qualname=qualname,
            line=node.lineno,  # type: ignore[attr-defined]
            end_line=getattr(node, "end_lineno", None),
            signature=_function_signature(node, is_async=is_async),
            docstring=ast.get_docstring(node),  # type: ignore[arg-type]
            decorators=tuple(_dotted_name(d) for d in node.decorator_list),  # type: ignore[attr-defined]
            parent_uid=parent_uid if parent_uid != module_uid(self.module_name) else None,
            is_method=in_class,
        )
        self.decls.append(decl)
        self.symbols_by_name[name] = uid

        for dec in node.decorator_list:  # type: ignore[attr-defined]
            self.decorators_edges.append((uid, _dotted_name(dec)))

        # TASK-083: collect param + return type annotations.
        for ann_name in _function_param_annotations(node):
            self.param_types.append((uid, ann_name))
        ret_ann = _function_return_annotation(node)
        if ret_ann:
            self.return_types.append((uid, ret_ann))

        self._scope_uid_stack.append(uid)
        try:
            # Walk the body for two things: nested decls (visit them so we
            # emit code:function / code:method nodes with full qualnames)
            # AND Call nodes (emit call edges scoped to this function).
            for child in node.body:  # type: ignore[attr-defined]
                if isinstance(
                    child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
                ):
                    self.visit(child)
                else:
                    self._walk_calls(child)
        finally:
            self._scope_uid_stack.pop()
            self._pop_qual()

    def _walk_calls(self, node: ast.AST) -> None:
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call):
                target = _dotted_name(sub.func)
                if not target:
                    continue
                last_segment = target.split(".")[-1]
                is_ctor = last_segment[:1].isupper()
                self.calls.append(
                    _CallSite(
                        caller_uid=self._scope_uid_stack[-1],
                        callee_name=last_segment,
                        full_expr=target,
                        line=sub.lineno,
                        is_constructor_like=is_ctor,
                    )
                )

    # -- qualname stack helpers --------------------------------------------

    def _push_qual(self, name: str) -> str:
        self._qualname_stack.append(name)
        return ".".join(self._qualname_stack)

    def _pop_qual(self) -> None:
        self._qualname_stack.pop()


# ---------------------------------------------------------------------------
# Resolution helpers
# ---------------------------------------------------------------------------


def _resolve_symbol(name: str, *, path: str, visitor: _PythonVisitor) -> str:
    """Best-effort resolution of a bare / dotted name to a uid.

    Step 1: same-scope name map (visitor.symbols_by_name).
    Step 2: imported_local_names (explicit imports).
    Fallback: a synthetic external uid keeps downstream stubs happy.
    """
    root = name.split(".")[0]
    if root in visitor.symbols_by_name:
        return visitor.symbols_by_name[root]
    imp = visitor.imported_local_names.get(root)
    if imp is not None:
        target_mod = imp.source_module or imp.imported
        return f"code:external:{target_mod}:{imp.imported}"
    return f"code:external:unresolved:{name}"


def _resolve_call(
    call: _CallSite,
    *,
    visitor: _PythonVisitor,
    path: str,
) -> tuple[float, tuple[EvidenceSignal, ...], str]:
    """Return (confidence, evidence, resolved_uid) for a call-site.

    Implements the pure-Python subset of the 7-step lookup:
      step 1 (same_scope)     → 0.5
      step 2 (enclosing)      → 0.3 (module-scoped name)
      step 3 (explicit_import)→ 0.4
    Everything else falls to 0.3 unresolved.
    """
    signals: list[EvidenceSignal] = []
    confidence = 0.0

    if call.callee_name in visitor.symbols_by_name:
        signals.append(EvidenceSignal("same_scope", 0.5))
        confidence += 0.5
        resolved = visitor.symbols_by_name[call.callee_name]
    elif call.callee_name in visitor.imported_local_names:
        imp = visitor.imported_local_names[call.callee_name]
        signals.append(EvidenceSignal("explicit_import", 0.4, note=imp.source_module))
        confidence += 0.4
        target_mod = imp.source_module or imp.imported
        resolved = f"code:external:{target_mod}:{imp.imported}"
    elif "." in call.full_expr and call.full_expr.split(".")[0] in visitor.imported_local_names:
        # Dotted call like `mod.foo()` where `mod` was imported.
        root = call.full_expr.split(".")[0]
        imp = visitor.imported_local_names[root]
        signals.append(EvidenceSignal("explicit_import", 0.4, note=imp.source_module))
        confidence += 0.4
        tail = ".".join(call.full_expr.split(".")[1:])
        target_mod = imp.source_module or imp.imported
        resolved = f"code:external:{target_mod}:{tail}"
    else:
        signals.append(EvidenceSignal("unresolved_call", 0.3))
        confidence = 0.3
        resolved = f"code:external:unresolved:{call.full_expr}"

    return (round(min(confidence, 1.0), 4), tuple(signals), resolved)


def _inherit_confidence(base_name: str, visitor: _PythonVisitor) -> float:
    if base_name.split(".")[0] in visitor.symbols_by_name:
        return 0.95
    if base_name.split(".")[0] in visitor.imported_local_names:
        return 0.8
    return 0.5


def _decorator_confidence(name: str, visitor: _PythonVisitor) -> float:
    if name.split(".")[0] in visitor.symbols_by_name:
        return 0.9
    if name.split(".")[0] in visitor.imported_local_names:
        return 0.85
    return 0.6


def _annotation_confidence(type_name: str, visitor: _PythonVisitor) -> float:
    """Confidence for has_param_type / returns_type / field_of_type edges.

    Mirrors `_inherit_confidence` but slightly stricter: same-scope
    binding wins (0.95 — directly observed declaration), explicit
    import next (0.85 — origin is known but not the symbol body),
    builtin / unresolved fall back to 0.3 so consumers know the edge
    is best-effort.
    """
    head = type_name.split(".")[0]
    if head in visitor.symbols_by_name:
        return 0.95
    if head in visitor.imported_local_names:
        return 0.85
    if head in _BUILTIN_TYPES:
        # Edges to bare builtins are still useful (UI heat-maps), but
        # they should not win against any user-resolved type.
        return 0.7
    return 0.3


_BUILTIN_TYPES: frozenset[str] = frozenset({
    "str", "int", "float", "bool", "bytes", "list", "dict", "tuple",
    "set", "frozenset", "None", "Any", "object", "type", "complex",
    "range", "memoryview", "bytearray", "Path", "datetime", "date",
    "time", "timedelta", "Decimal",
})


# ---------------------------------------------------------------------------
# Misc helpers
# ---------------------------------------------------------------------------


def _module_name_for_path(path: str) -> str:
    """Derive a dotted module name from a file path.

    Resolution order:
      1. Active ToolchainContext (TASK-082): when pyproject.toml /
         setup.cfg declare a non-standard package root (e.g.
         ``[tool.poetry.packages] include="myapp" from="packages"``),
         honour it so `packages/myapp/auth.py` → `myapp.auth`.
      2. Hard-coded ``src/`` / ``core/`` strip — keeps coding-os and
         most src-layout projects working without a config file.
      3. Fall through: full POSIX path with `.py` and `__init__` removed.
    """
    parts = [p for p in _normalize_path(path).split("/") if p]
    if parts and parts[-1].endswith(".py"):
        parts[-1] = parts[-1][: -len(".py")]
    if parts and parts[-1] == "__init__":
        parts.pop()

    # 1. Toolchain-driven package root.
    rebased = _toolchain_python_module_parts(parts)
    if rebased is not None:
        return ".".join(rebased) or "__root__"

    # 2. Default repo-root shims.
    if parts and parts[0] in {"src", "core"}:
        parts = parts[1:]
    return ".".join(parts) or "__root__"


def _toolchain_python_module_parts(parts: list[str]) -> list[str] | None:
    """Try to rebase a file's path-parts under a known Python package
    root from the active ToolchainContext.  Returns the rebased parts
    (e.g. ``["myapp", "auth"]``) or None when no package root matches.
    """
    try:
        from ..toolchain import get_active
    except ImportError:
        return None
    ctx = get_active()
    if ctx is None:
        return None
    if not ctx.python_packages:
        return None
    flat = "/".join(parts)
    # Match longest root first so nested packages win over shallow ones.
    for pkg_name, pkg_root in sorted(
        ctx.python_packages.items(), key=lambda kv: -len(kv[1])
    ):
        rel_root = pkg_root.strip("/").replace("\\", "/")
        if not rel_root:
            continue
        prefix = f"{rel_root}/"
        if flat.startswith(prefix):
            tail = flat[len(prefix):]
            tail_parts = [p for p in tail.split("/") if p]
            return [pkg_name, *tail_parts]
        if flat == rel_root:
            return [pkg_name]
    return None


def _hash_decl(decl: _SymbolDecl) -> str:
    key = f"{decl.kind}|{decl.uid}|{decl.signature}|{decl.decorators}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def _class_signature(node: ast.ClassDef) -> str:
    bases = ", ".join(_dotted_name(b) for b in node.bases)
    return f"class {node.name}({bases})" if bases else f"class {node.name}"


def _function_param_annotations(node: ast.AST) -> list[str]:
    """Return the annotation names for every annotated parameter of
    ``node`` (a FunctionDef / AsyncFunctionDef).

    Skips `self` and `cls` because their annotation is uninteresting
    (it would always be the surrounding class), and skips parameters
    with no annotation.  Union-style annotations expand to one entry
    per branch so each receiver type emits its own edge.
    """
    args = getattr(node, "args", None)
    if args is None:
        return []
    out: list[str] = []
    pos_args = list(getattr(args, "posonlyargs", []) or []) + list(
        getattr(args, "args", []) or []
    )
    for idx, arg in enumerate(pos_args):
        if idx == 0 and arg.arg in ("self", "cls"):
            continue
        if arg.annotation is None:
            continue
        out.extend(_expand_annotation(arg.annotation))
    for arg in getattr(args, "kwonlyargs", []) or []:
        if arg.annotation is None:
            continue
        out.extend(_expand_annotation(arg.annotation))
    if getattr(args, "vararg", None) is not None and args.vararg.annotation is not None:
        out.extend(_expand_annotation(args.vararg.annotation))
    if getattr(args, "kwarg", None) is not None and args.kwarg.annotation is not None:
        out.extend(_expand_annotation(args.kwarg.annotation))
    return out


def _function_return_annotation(node: ast.AST) -> str | None:
    ret = getattr(node, "returns", None)
    if ret is None:
        return None
    flat = _expand_annotation(ret)
    return flat[0] if flat else None


def _expand_annotation(node: ast.AST) -> list[str]:
    """Return one or more dotted names for an annotation node.

    `Foo`                  → ["Foo"]
    `pkg.Foo`              → ["pkg.Foo"]
    `Optional[Foo]`        → ["Foo"]            (None branch dropped)
    `Union[Foo, Bar]`      → ["Foo", "Bar"]
    `Foo | Bar`            → ["Foo", "Bar"]
    `list[Foo]`            → ["Foo"]            (container stripped)
    `Literal["x"]`         → []                 (value-only types skipped)

    Anything we can't recognise yields an empty list — caller will then
    skip the edge entirely rather than emit a stub with bad confidence.
    """
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, ast.Attribute):
        dotted = _dotted_name(node)
        return [dotted] if dotted else []
    if isinstance(node, ast.Constant):
        # `None` annotation → drop (often appears via Optional[...]).
        if node.value is None:
            return []
        # Forward reference as string literal: `"Foo"`.
        if isinstance(node.value, str):
            return [node.value]
        return []
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        # PEP 604 unions: `Foo | Bar | None`.
        return _expand_annotation(node.left) + _expand_annotation(node.right)
    if isinstance(node, ast.Subscript):
        # Container subscripts: `list[Foo]`, `Optional[Foo]`, `Union[Foo, Bar]`,
        # `dict[str, Foo]`.  Walk inside and recurse.
        value_name = _dotted_name(node.value) if isinstance(node.value, (ast.Name, ast.Attribute)) else ""
        slice_node = getattr(node, "slice", None)
        if slice_node is None:
            return []
        # Generic strip — unwrap the container, recurse on the slice.
        if isinstance(slice_node, ast.Tuple):
            return [t for elt in slice_node.elts for t in _expand_annotation(elt)]
        # Special case for `Literal[...]` — types-by-value, not by-class.
        if value_name == "Literal":
            return []
        return _expand_annotation(slice_node)
    if isinstance(node, ast.Tuple):
        return [t for elt in node.elts for t in _expand_annotation(elt)]
    return []


def _function_signature(node: ast.AST, *, is_async: bool) -> str:
    try:
        args = ast.unparse(node.args)  # type: ignore[attr-defined]
    except (AttributeError, TypeError):
        args = ""
    prefix = "async def" if is_async else "def"
    return f"{prefix} {node.name}({args})"  # type: ignore[attr-defined]


def _dotted_name(node: ast.AST) -> str:
    """Best-effort string form of an expression node (Name / Attribute / Call)."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_dotted_name(node.value)}.{node.attr}"
    if isinstance(node, ast.Call):
        return _dotted_name(node.func)
    if isinstance(node, ast.Subscript):
        return _dotted_name(node.value)
    try:
        return ast.unparse(node)
    except Exception:  # noqa: BLE001
        return "<expr>"


__all__ = [
    "EXTRACTOR_ID",
    "extract",
    "file_uid",
    "module_uid",
    "class_uid",
    "function_uid",
    "method_uid",
]
