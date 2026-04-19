"""graph-os — Python extractor (I.4).

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
)

logger = logging.getLogger("graph_os.extractors.code_python")

EXTRACTOR_ID = "code_python@v1"


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
        _promote_stubs(result)
        return result
    except Exception as exc:  # noqa: BLE001
        result.parse_errors.append(ParseError(kind="fatal", detail=str(exc)))
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
    for subclass_uid, base_name in visitor.inherits:
        result.edges.append(
            GraphEdge(
                source_uid=subclass_uid,
                target_uid=_resolve_symbol(
                    base_name, path=normalised, visitor=visitor
                ),
                edge_type="inherits_from",
                extractor=EXTRACTOR_ID,
                confidence=_inherit_confidence(base_name, visitor),
                source_span=f"{normalised}",
                evidence=(EvidenceSignal("ast_base_class", 0.9),),
            )
        )

    # Decorators — is_decorated_by.
    for decorated_uid, dec_name in visitor.decorators_edges:
        result.edges.append(
            GraphEdge(
                source_uid=decorated_uid,
                target_uid=_resolve_symbol(
                    dec_name, path=normalised, visitor=visitor
                ),
                edge_type="is_decorated_by",
                extractor=EXTRACTOR_ID,
                confidence=_decorator_confidence(dec_name, visitor),
                evidence=(EvidenceSignal("ast_decorator", 0.9),),
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
                    "extractor": EXTRACTOR_ID,
                },
            )
        )
        result.edges.append(
            GraphEdge(
                source_uid=mod_node.uid,
                target_uid=imp_uid,
                edge_type="contains",
                extractor=EXTRACTOR_ID,
                confidence=1.0,
            )
        )
        target_mod = imp.source_module or imp.imported
        result.edges.append(
            GraphEdge(
                source_uid=mod_node.uid,
                target_uid=module_uid(target_mod),
                edge_type="imports",
                extractor=EXTRACTOR_ID,
                confidence=0.9,
                source_span=f"{normalised}:{imp.line}",
                evidence=(EvidenceSignal("ast_import", 0.9),),
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


# ---------------------------------------------------------------------------
# Misc helpers
# ---------------------------------------------------------------------------


def _module_name_for_path(path: str) -> str:
    """Derive a dotted module name from a file path.

    Non-rigorous — drops `src/`, `core/`, and the `.py` suffix. The
    LSP overlay (I.5) refines this with the project's real Python path
    resolution (pyproject + site-packages).
    """
    parts = [p for p in _normalize_path(path).split("/") if p]
    if parts and parts[-1].endswith(".py"):
        parts[-1] = parts[-1][: -len(".py")]
    if parts and parts[-1] == "__init__":
        parts.pop()
    # Strip common repo-root shims.
    if parts and parts[0] in {"src", "core"}:
        parts = parts[1:]
    return ".".join(parts) or "__root__"


def _hash_decl(decl: _SymbolDecl) -> str:
    key = f"{decl.kind}|{decl.uid}|{decl.signature}|{decl.decorators}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def _class_signature(node: ast.ClassDef) -> str:
    bases = ", ".join(_dotted_name(b) for b in node.bases)
    return f"class {node.name}({bases})" if bases else f"class {node.name}"


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
