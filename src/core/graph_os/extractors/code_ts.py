"""graph_os — TypeScript / TSX extractor (I.6).

DEPENDS:  stdlib regex only.
"""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import PurePosixPath
from typing import Any

from ..types import EvidenceSignal, GraphEdge, GraphNode
from .md_links import (
    ExtractionResult,
    ParseError,
    _normalize_path,
    _promote_stubs,
    emit_contains_spine,
)

logger = logging.getLogger("graph_os.extractors.code_ts")

EXTRACTOR_ID = "code_ts@v1"
# TASK-121: tree-sitter primary path for TS/TSX. Activated by
# COS_EXTRACTOR_PREFERENCE=tree-sitter when the grammar is installed.
EXTRACTOR_ID_TS = "code_ts_ts@v1"


def _tree_sitter_ts_active(lang_id: str) -> bool:
    """True when imports / heritage should be tagged as tree-sitter.

    Activation conditions:
      - COS_EXTRACTOR_PREFERENCE == "tree-sitter"
      - the requested language grammar (typescript / tsx) is loadable

    Default `auto` mode keeps the legacy regex tag so existing graphs
    don't double-emit during rollout.
    """
    import os as _os

    pref = (_os.environ.get("COS_EXTRACTOR_PREFERENCE") or "auto").lower()
    if pref != "tree-sitter":
        return False
    try:
        from ..tree_sitter_overlay import _load_language

        return _load_language(lang_id) is not None
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Comment / string stripping — simple but enough for a scanner.
# ---------------------------------------------------------------------------

_LINE_COMMENT_RE = re.compile(r"//[^\n]*")
_BLOCK_COMMENT_RE = re.compile(r"/\*[\s\S]*?\*/")
_STRING_RE = re.compile(r"""(?P<q>['"`])(?:\\.|(?!(?P=q)).)*(?P=q)""")

# Declarations.
_IMPORT_RE = re.compile(
    r"""^\s*
    import
    \s+
    (?:type\s+)?                                  # `import type`
    (?P<clause>
        \{[^{}]*\}                                 # { a, b as c }
      | [A-Za-z_$][\w$]*                           # default import
      | \*\s+as\s+[A-Za-z_$][\w$]*                 # * as ns
    )
    (?:\s*,\s*\{[^{}]*\})?
    \s+from\s+
    ['"](?P<module>[^'"]+)['"]
    """,
    re.VERBOSE | re.MULTILINE,
)
_SIDE_EFFECT_IMPORT_RE = re.compile(r"""^\s*import\s+['"](?P<module>[^'"]+)['"]""", re.MULTILINE)
# E7: dynamic import — `import('./mod')` and `await import('./mod')`.
# Used heavily for code-splitting / lazy routes; previously invisible.
_DYNAMIC_IMPORT_RE = re.compile(
    r"""(?<![\w$])(?:await\s+)?import\s*\(\s*['"](?P<module>[^'"]+)['"]\s*\)""",
    re.MULTILINE,
)
_EXPORT_FROM_RE = re.compile(
    r"""^\s*export\s+(?:\*|\{[^{}]*\})\s+from\s+['"](?P<module>[^'"]+)['"]""",
    re.MULTILINE,
)

_CLASS_RE = re.compile(
    r"""^\s*(?:export\s+(?:default\s+)?)?(?:abstract\s+)?class\s+
        (?P<name>[A-Za-z_$][\w$]*)
        (?:\s+extends\s+(?P<parent>[A-Za-z_$][\w$.]*))?
        (?:\s+implements\s+(?P<implements>[^{]+?))?
        \s*\{
    """,
    re.VERBOSE | re.MULTILINE,
)
_INTERFACE_RE = re.compile(
    r"""^\s*(?:export\s+)?interface\s+
        (?P<name>[A-Za-z_$][\w$]*)
        (?:\s+extends\s+(?P<parents>[^{]+?))?
        \s*\{
    """,
    re.VERBOSE | re.MULTILINE,
)
_FUNCTION_RE = re.compile(
    r"""^\s*(?:export\s+(?:default\s+)?)?(?:async\s+)?function\s+
        (?P<name>[A-Za-z_$][\w$]*)
        (?P<generics><[^>]*>)?
        \s*\(
    """,
    re.VERBOSE | re.MULTILINE,
)
_ARROW_RE = re.compile(
    r"""^\s*(?:export\s+(?:default\s+)?)?
        (?:const|let|var)\s+
        (?P<name>[A-Za-z_$][\w$]*)
        \s*(?::[^=]+)?\s*=\s*
        (?:async\s+)?
        (?:<[^>]*>)?
        \s*\(
    """,
    re.VERBOSE | re.MULTILINE,
)
_METHOD_RE = re.compile(
    r"""^\s*(?:public|protected|private|readonly|async|static|\s)*\s*
        (?P<name>[A-Za-z_$][\w$]*)
        (?P<generics><[^>]*>)?
        \s*\(
    """,
    re.VERBOSE | re.MULTILINE,
)

# Call-site scanner — looks for `name(` and `name.something(`.
_CALL_RE = re.compile(
    r"""(?<![.\w$])
        (?P<target>[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)
        \s*\(
    """,
    re.VERBOSE,
)
# JSX component usage — uppercase tag => React component.
_JSX_COMPONENT_RE = re.compile(r"<(?P<name>[A-Z][A-Za-z0-9_]*)\b")

# Decorator — lands on the *next* decl.
_DECORATOR_RE = re.compile(
    r"""^\s*@(?P<target>[A-Za-z_$][\w$.]*)
        (?:\s*\([^)]*\))?\s*$
    """,
    re.VERBOSE | re.MULTILINE,
)


# ---------------------------------------------------------------------------
# uid helpers
# ---------------------------------------------------------------------------


def file_uid(path: str) -> str:
    return f"code:file:{_normalize_path(path)}"


def module_uid(path: str) -> str:
    # TS modules identify by file path — no package system by default.
    return f"code:module:{_normalize_path(path)}"


def class_uid(path: str, name: str) -> str:
    return f"code:class:{_normalize_path(path)}::{name}"


def interface_uid(path: str, name: str) -> str:
    return f"code:interface:{_normalize_path(path)}::{name}"


def function_uid(path: str, name: str) -> str:
    return f"code:function:{_normalize_path(path)}::{name}"


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Tree-sitter AST walker (parity path). Used when the TS/TSX grammar is
# available — emits the SAME node/edge shapes as the regex extractors but
# AST-accurate: class/interface/function/arrow/method nodes, calls sourced
# at the enclosing scope (regex can't determine scope), inherits_from /
# implements, param/return type edges, and JSX component constructs. The
# regex path (below) stays the fallback for grammar-less installs.
# ---------------------------------------------------------------------------


def _ts_name(node: Any) -> str:
    if node is None:
        return ""
    n = node.child_by_field_name("name")
    return n.text.decode("utf-8", "replace") if n is not None else ""


def _ts_line(node: Any) -> int:
    return int(node.start_point[0]) + 1


def _ts_type_head(type_annotation_node: Any) -> str:
    if type_annotation_node is None:
        return ""
    for c in type_annotation_node.children:
        if c.type != ":":
            txt = c.text.decode("utf-8", "replace").strip()
            return txt.split("<")[0].split("[")[0].split("|")[0].strip()
    return ""


def _ts_method_uid(path: str, cls: str, name: str) -> str:
    return f"code:method:{path}::{cls}.{name}"


def _ts_resolve_type(name: str, imported_names: dict[str, str], local_names: dict[str, str]) -> str:
    head = name.split("<")[0].split(".")[0].strip()
    if head in local_names:
        return local_names[head]
    if head in imported_names:
        return f"code:external:{imported_names[head]}:{head}"
    return f"code:external:unresolved:{head}"


def _ts_decorator_name(dec: Any) -> str:
    for c in dec.children:
        if c.type in ("identifier", "member_expression"):
            return c.text.decode("utf-8", "replace")
        if c.type == "call_expression":
            fn = c.child_by_field_name("function")
            if fn is not None:
                return fn.text.decode("utf-8", "replace")
    return ""


def _ts_callee(fn_field: Any) -> tuple[str, str]:
    """(dotted_target, head_identifier) for a call's function node.

    Reduces chained / multiline expressions (`a().b().join`, `/re/.test`)
    to a simple ``obj.method`` or bare name so uids never contain newlines
    or punctuation — the source of the malformed_uid_path regression.
    """
    t = fn_field.type
    if t == "identifier":
        nm = fn_field.text.decode("utf-8", "replace")
        return nm, nm
    if t == "member_expression":
        prop = fn_field.child_by_field_name("property")
        propname = prop.text.decode("utf-8", "replace") if prop is not None else ""
        obj = fn_field.child_by_field_name("object")
        root = obj
        while root is not None and root.type == "member_expression":
            root = root.child_by_field_name("object")
        headname = (
            root.text.decode("utf-8", "replace")
            if (root is not None and root.type in ("identifier", "this", "super"))
            else ""
        )
        if headname and len(headname) < 40 and "\n" not in headname:
            return f"{headname}.{propname}", headname
        return propname, propname
    return "", ""


def _ts_enclosing_class_uid(node: Any, path: str) -> str | None:
    cur = node.parent
    while cur is not None:
        if cur.type in ("class_declaration", "abstract_class_declaration", "class"):
            nm = _ts_name(cur)
            return class_uid(path, nm) if nm else None
        cur = cur.parent
    return None


def _ts_enclosing_scope(node: Any, path: str) -> str | None:
    cur = node.parent
    while cur is not None:
        t = cur.type
        if t in ("function_declaration", "generator_function_declaration"):
            nm = _ts_name(cur)
            if nm:
                return function_uid(path, nm)
        elif t == "method_definition":
            mn = _ts_name(cur)
            cls = cur.parent
            while cls is not None and cls.type not in (
                "class_declaration", "abstract_class_declaration", "class"
            ):
                cls = cls.parent
            cn = _ts_name(cls) if cls is not None else ""
            if mn and cn:
                return _ts_method_uid(path, cn, mn)
        elif t in ("arrow_function", "function", "function_expression"):
            p = cur.parent
            if p is not None and p.type == "variable_declarator":
                nm = _ts_name(p)
                if nm:
                    return function_uid(path, nm)
        cur = cur.parent
    return None


def _ts_emit_type_edges(
    fn_node: Any, *, owner_uid: str, path: str, pending: list[tuple[str, str, str, int]]
) -> None:
    """Collect (owner_uid, type_name, edge_type, line) for deferred resolution.

    Resolution is deferred to after Pass A so a param/return type that
    references a class/interface declared later in the file still binds to
    the real local uid (Python-parity — code_python resolves annotations
    against the complete ``symbols_by_name`` at emit time).
    """
    params = fn_node.child_by_field_name("parameters")
    if params is not None:
        for p in params.children:
            if p.type not in ("required_parameter", "optional_parameter"):
                continue
            ta = p.child_by_field_name("type")
            if ta is None:
                ta = next((c for c in p.children if c.type == "type_annotation"), None)
            tname = _ts_type_head(ta)
            if tname and tname[:1].isalpha():
                pending.append((owner_uid, tname, "has_param_type", _ts_line(p)))
    rt = fn_node.child_by_field_name("return_type")
    tname = _ts_type_head(rt)
    if tname and tname[:1].isalpha() and tname not in ("void", "any", "unknown", "never", "Promise"):
        pending.append((owner_uid, tname, "returns_type", _ts_line(fn_node)))


def _walk_ts_symbols(
    root: Any,
    *,
    path: str,
    module_uid_: str,
    file_uid_: str,
    lang: str,
    imported_names: dict[str, str],
    local_names: dict[str, str],
    result: ExtractionResult,
) -> None:
    """AST-accurate symbol/edge extraction from a tree-sitter TS/TSX tree."""
    from ..tree_sitter_overlay import iter_nodes

    # GE: per-class method map so `this.method()` resolves to THIS class's
    # method instead of an unresolved stub (matters for class-heavy TS:
    # NestJS / Angular). Populated in the class-body method loop below.
    methods_by_class: dict[str, dict[str, str]] = {}
    # Deferred type-annotation edges — resolved after Pass A (see below).
    pending_types: list[tuple[str, str, str, int]] = []

    # ---- Pass A: declarations (populate local_names before resolving calls) ----
    for fn in iter_nodes(root, {"function_declaration", "generator_function_declaration"}):
        name = _ts_name(fn)
        if not name:
            continue
        uid = function_uid(path, name)
        result.nodes.append(GraphNode(
            uid=uid, kind="code:function", label=name, file_path=path,
            start_line=_ts_line(fn), signature=f"function {name}(…)", lang=lang,
            metadata={"extractor": EXTRACTOR_ID_TS}))
        local_names[name] = uid
        result.edges.append(GraphEdge(source_uid=module_uid_, target_uid=uid,
            edge_type="contains", extractor=EXTRACTOR_ID_TS, confidence=1.0))
        _ts_emit_type_edges(fn, owner_uid=uid, path=path, pending=pending_types)

    for vd in iter_nodes(root, {"variable_declarator"}):
        val = vd.child_by_field_name("value")
        if val is None or val.type not in ("arrow_function", "function", "function_expression"):
            continue
        name = _ts_name(vd)
        if not name or name in local_names:
            continue
        uid = function_uid(path, name)
        result.nodes.append(GraphNode(
            uid=uid, kind="code:function", label=name, file_path=path,
            start_line=_ts_line(vd), signature=f"const {name} = (…) =>", lang=lang,
            metadata={"extractor": EXTRACTOR_ID_TS, "arrow": True}))
        local_names[name] = uid
        result.edges.append(GraphEdge(source_uid=module_uid_, target_uid=uid,
            edge_type="contains", extractor=EXTRACTOR_ID_TS, confidence=1.0))
        _ts_emit_type_edges(val, owner_uid=uid, path=path, pending=pending_types)

    for it in iter_nodes(root, {"interface_declaration"}):
        name = _ts_name(it)
        if not name:
            continue
        uid = interface_uid(path, name)
        result.nodes.append(GraphNode(
            uid=uid, kind="code:interface", label=name, file_path=path,
            start_line=_ts_line(it), signature=f"interface {name}", lang=lang,
            metadata={"extractor": EXTRACTOR_ID_TS}))
        local_names[name] = uid
        result.edges.append(GraphEdge(source_uid=module_uid_, target_uid=uid,
            edge_type="contains", extractor=EXTRACTOR_ID_TS, confidence=1.0))
        ext = next((c for c in it.children if c.type == "extends_type_clause"), None)
        if ext is not None:
            for t in ext.children:
                if t.type in ("type_identifier", "identifier", "generic_type"):
                    result.edges.append(GraphEdge(
                        source_uid=uid,
                        target_uid=_ts_resolve_type(
                            t.text.decode("utf-8", "replace"), imported_names, local_names),
                        edge_type="extends", extractor=EXTRACTOR_ID_TS, confidence=0.8,
                        source_span=f"{path}:{_ts_line(ext)}"))

    for ta in iter_nodes(root, {"type_alias_declaration"}):
        name = _ts_name(ta)
        if not name or name in local_names:
            continue
        uid = interface_uid(path, name)
        result.nodes.append(GraphNode(
            uid=uid, kind="code:interface", label=name, file_path=path,
            start_line=_ts_line(ta), signature=f"type {name}", lang=lang,
            metadata={"extractor": EXTRACTOR_ID_TS, "type_alias": True}))
        local_names[name] = uid
        result.edges.append(GraphEdge(source_uid=module_uid_, target_uid=uid,
            edge_type="contains", extractor=EXTRACTOR_ID_TS, confidence=1.0))

    for cls in iter_nodes(root, {"class_declaration", "abstract_class_declaration"}):
        name = _ts_name(cls)
        if not name:
            continue
        cuid = class_uid(path, name)
        result.nodes.append(GraphNode(
            uid=cuid, kind="code:class", label=name, file_path=path,
            start_line=_ts_line(cls), signature=f"class {name}", lang=lang,
            metadata={"extractor": EXTRACTOR_ID_TS}))
        local_names[name] = cuid
        result.edges.append(GraphEdge(source_uid=module_uid_, target_uid=cuid,
            edge_type="contains", extractor=EXTRACTOR_ID_TS, confidence=1.0))
        # Decorators may be children of the class OR of the wrapping
        # `export_statement` (`@Dec()\nexport class C`). Scan both.
        _dec_nodes = list(cls.children)
        if cls.parent is not None and cls.parent.type == "export_statement":
            _dec_nodes += list(cls.parent.children)
        _seen_dec: set[str] = set()
        for dec in _dec_nodes:
            if dec.type != "decorator":
                continue
            dname = _ts_decorator_name(dec)
            if dname and dname not in _seen_dec:
                _seen_dec.add(dname)
                result.edges.append(GraphEdge(
                    source_uid=cuid,
                    target_uid=_ts_resolve_type(dname, imported_names, local_names),
                    edge_type="is_decorated_by", extractor=EXTRACTOR_ID_TS, confidence=0.85,
                    source_span=f"{path}:{_ts_line(dec)}"))
        heritage = next((c for c in cls.children if c.type == "class_heritage"), None)
        if heritage is not None:
            for clause in heritage.children:
                etype = "inherits_from" if clause.type == "extends_clause" else (
                    "implements" if clause.type == "implements_clause" else None)
                if etype is None:
                    continue
                for t in clause.children:
                    if t.type in ("identifier", "type_identifier", "member_expression", "generic_type"):
                        base = t.text.decode("utf-8", "replace")
                        result.edges.append(GraphEdge(
                            source_uid=cuid,
                            target_uid=_ts_resolve_type(base, imported_names, local_names),
                            edge_type=etype, extractor=EXTRACTOR_ID_TS, confidence=0.8,
                            source_span=f"{path}:{_ts_line(clause)}"))
        body = next((c for c in cls.children if c.type == "class_body"), None)
        if body is not None:
            for m in body.children:
                if m.type != "method_definition":
                    continue
                mname = _ts_name(m)
                if not mname:
                    continue
                muid = _ts_method_uid(path, name, mname)
                methods_by_class.setdefault(cuid, {})[mname] = muid
                result.nodes.append(GraphNode(
                    uid=muid, kind="code:method", label=mname, file_path=path,
                    start_line=_ts_line(m), signature=f"{name}.{mname}(…)", lang=lang,
                    metadata={"extractor": EXTRACTOR_ID_TS}))
                result.edges.append(GraphEdge(source_uid=cuid, target_uid=muid,
                    edge_type="contains", extractor=EXTRACTOR_ID_TS, confidence=1.0))
                for dec in m.children:
                    if dec.type != "decorator":
                        continue
                    dname = _ts_decorator_name(dec)
                    if dname:
                        result.edges.append(GraphEdge(
                            source_uid=muid,
                            target_uid=_ts_resolve_type(dname, imported_names, local_names),
                            edge_type="is_decorated_by", extractor=EXTRACTOR_ID_TS,
                            confidence=0.85, source_span=f"{path}:{_ts_line(dec)}"))
                _ts_emit_type_edges(m, owner_uid=muid, path=path, pending=pending_types)

    # ---- enum / namespace declarations (queryable type-like nodes) ----
    for en in iter_nodes(root, {"enum_declaration"}):
        name = _ts_name(en)
        if not name or name in local_names:
            continue
        uid = class_uid(path, name)
        result.nodes.append(GraphNode(
            uid=uid, kind="code:class", label=name, file_path=path,
            start_line=_ts_line(en), signature=f"enum {name}", lang=lang,
            metadata={"extractor": EXTRACTOR_ID_TS, "ts_kind": "enum"}))
        local_names[name] = uid
        result.edges.append(GraphEdge(source_uid=module_uid_, target_uid=uid,
            edge_type="contains", extractor=EXTRACTOR_ID_TS, confidence=1.0))

    for ns in iter_nodes(root, {"internal_module"}):
        name = _ts_name(ns)
        if not name or name in local_names:
            continue
        uid = class_uid(path, name)
        result.nodes.append(GraphNode(
            uid=uid, kind="code:class", label=name, file_path=path,
            start_line=_ts_line(ns), signature=f"namespace {name}", lang=lang,
            metadata={"extractor": EXTRACTOR_ID_TS, "ts_kind": "namespace"}))
        local_names[name] = uid
        result.edges.append(GraphEdge(source_uid=module_uid_, target_uid=uid,
            edge_type="contains", extractor=EXTRACTOR_ID_TS, confidence=1.0))

    # ---- resolve deferred type edges (local_names now complete) ----
    for owner_uid, tname, etype, line in pending_types:
        target = _ts_resolve_type(tname, imported_names, local_names)
        conf = (
            0.8
            if target.startswith(("code:class:", "code:interface:", "code:function:"))
            else 0.5
        )
        result.edges.append(GraphEdge(
            source_uid=owner_uid, target_uid=target, edge_type=etype,
            extractor=EXTRACTOR_ID_TS, confidence=conf,
            source_span=f"{path}:{line}",
            evidence=(EvidenceSignal("ts_annotation", conf),)))

    # ---- Pass B: calls / constructs sourced at the enclosing scope ----
    for call in iter_nodes(root, {"call_expression", "new_expression"}):
        fn_field = call.child_by_field_name("function") or call.child_by_field_name("constructor")
        if fn_field is None:
            fn_field = call.children[0] if call.children else None
        if fn_field is None:
            continue
        target, head = _ts_callee(fn_field)
        if not target or not re.match(r"^[\w$.]+$", target) or head in _TS_KEYWORDS:
            continue
        is_new = call.type == "new_expression"
        is_ctor = is_new or (target.split(".")[-1][:1].isupper())
        is_await = call.parent is not None and call.parent.type == "await_expression"
        src = _ts_enclosing_scope(call, path) or module_uid_
        if head == "this" and "." in target:
            # GE: this.method() → enclosing class's method (else unresolved).
            encl_cls = _ts_enclosing_class_uid(call, path)
            mname = target.split(".", 1)[1].split(".")[0]
            m_uid = methods_by_class.get(encl_cls or "", {}).get(mname)
            if m_uid:
                resolved, conf, sig = m_uid, 0.9, EvidenceSignal("this_method", 0.9)
            else:
                resolved, conf, sig = (
                    f"code:external:unresolved:{target}", 0.3, EvidenceSignal("unresolved_call", 0.3),
                )
        elif target in local_names:
            resolved, conf, sig = local_names[target], 0.9, EvidenceSignal("same_scope", 0.9)
        elif head in local_names and "." not in target:
            resolved, conf, sig = local_names[head], 0.9, EvidenceSignal("same_scope", 0.9)
        elif head in imported_names:
            specifier = imported_names[head]
            tail = ".".join(target.split(".")[1:]) or head
            resolved, conf = f"code:external:{specifier}:{tail}", 0.9
            sig = EvidenceSignal("explicit_import", 0.9, note=specifier)
        else:
            resolved, conf, sig = f"code:external:unresolved:{target}", 0.3, EvidenceSignal("unresolved_call", 0.3)
        edge_type = "awaits" if is_await else ("constructs" if is_ctor else "calls")
        result.edges.append(GraphEdge(
            source_uid=src, target_uid=resolved,
            edge_type=edge_type,
            extractor=EXTRACTOR_ID_TS, confidence=conf,
            source_span=f"{path}:{_ts_line(call)}", evidence=(sig,)))

    # ---- Pass C: JSX component usage (tsx) ----
    if lang == "tsx":
        for el in iter_nodes(root, {"jsx_opening_element", "jsx_self_closing_element"}):
            nm = el.child_by_field_name("name")
            comp = nm.text.decode("utf-8", "replace") if nm is not None else ""
            if not comp or not comp[:1].isupper():
                continue  # lowercase = host element (div / View) — skip
            head = comp.split(".")[0]
            if comp in local_names:
                resolved, conf = local_names[comp], 0.8
            elif head in imported_names:
                resolved, conf = f"code:external:{imported_names[head]}:{comp}", 0.7
            else:
                resolved, conf = f"code:external:unresolved:{comp}", 0.3
            result.edges.append(GraphEdge(
                source_uid=module_uid_, target_uid=resolved, edge_type="constructs",
                extractor=EXTRACTOR_ID_TS, confidence=conf,
                source_span=f"{path}:{_ts_line(el)}",
                evidence=(EvidenceSignal("jsx_component", conf),)))


def extract(path: str, content: str) -> ExtractionResult:
    """Parse a TS / TSX file → nodes + edges."""
    # Tree-sitter overlay pass (I.6b) — runs first to enrich AST-level
    # metadata. Regex scan below continues unchanged so results stay
    # backwards-compatible when the grammar is absent.
    try:
        from ..tree_sitter_overlay import parse as _ts_parse

        lang_id = "tsx" if path.endswith((".tsx", ".jsx")) else "typescript"
        _ts_overlay = _ts_parse(lang_id, content)
    except ImportError:
        _ts_overlay = None
    result = ExtractionResult()
    normalised = _normalize_path(path)
    lang = "tsx" if normalised.endswith((".tsx", ".jsx")) else "ts"
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]

    file_node = GraphNode(
        uid=file_uid(path),
        kind="code:file",
        label=PurePosixPath(normalised).name,
        file_path=normalised,
        lang=lang,
        content_hash=content_hash,
        metadata={"extractor": EXTRACTOR_ID},
    )
    result.nodes.append(file_node)

    try:
        import_scan = _strip_comments(content)
        decl_scan = _strip_comments_and_strings(content)
    except Exception as exc:
        result.parse_errors.append(ParseError(kind="fatal", detail=str(exc)))
        emit_contains_spine(
            file_path=path,
            file_uid_=file_node.uid,
            result=result,
            extractor_id=EXTRACTOR_ID,
        )
        _promote_stubs(result)
        return result

    overlay_meta: dict[str, object] = {}
    if _ts_overlay is not None:
        overlay_meta["ts_ast_nodes"] = _count_ts_nodes(_ts_overlay.root)
        overlay_meta["ts_language"] = _ts_overlay.language_id
    module = GraphNode(
        uid=module_uid(path),
        kind="code:module",
        label=PurePosixPath(normalised).stem,
        file_path=normalised,
        lang=lang,
        metadata={"extractor": EXTRACTOR_ID, **overlay_meta},
    )
    result.nodes.append(module)
    result.edges.append(
        GraphEdge(
            source_uid=file_node.uid,
            target_uid=module.uid,
            edge_type="contains",
            extractor=EXTRACTOR_ID,
            confidence=1.0,
        )
    )

    # TASK-121: tag imports as tree-sitter when the user opted in
    # AND the overlay parsed successfully (we already have a parsed
    # AST in `_ts_overlay`). The regex still extracts; the tag swap
    # signals "this came from grammar-validated TS" so the Hub UI
    # Inspector and provenance_for() consumers can distinguish.
    ts_override: str | None = None
    if _ts_overlay is not None and _tree_sitter_ts_active(lang_id):
        ts_override = EXTRACTOR_ID_TS

    imported_names = _extract_imports(
        path=normalised,
        module_uid_=module.uid,
        content=import_scan,
        result=result,
        extractor_override=ts_override,
    )
    local_names: dict[str, str] = {}
    if _ts_overlay is not None:
        # Parity path (default when grammar parsed): AST-accurate symbol/edge
        # extraction. Mirrors Python (ast) and Go (code_go@v2 tree-sitter).
        # Regex below is the fallback only when the grammar is unavailable.
        _walk_ts_symbols(
            _ts_overlay.root,
            path=normalised,
            module_uid_=module.uid,
            file_uid_=file_node.uid,
            lang=lang,
            imported_names=imported_names,
            local_names=local_names,
            result=result,
        )
    else:
        # Regex fallback (grammar absent) — backwards-compatible.
        _extract_classes(
            path=normalised,
            module_uid_=module.uid,
            lang=lang,
            content=decl_scan,
            result=result,
            local_names=local_names,
        )
        _extract_interfaces(
            path=normalised,
            module_uid_=module.uid,
            lang=lang,
            content=decl_scan,
            result=result,
            local_names=local_names,
        )
        _extract_functions(
            path=normalised,
            module_uid_=module.uid,
            lang=lang,
            content=decl_scan,
            result=result,
            local_names=local_names,
        )
        _extract_arrow_fns(
            path=normalised,
            module_uid_=module.uid,
            lang=lang,
            content=decl_scan,
            result=result,
            local_names=local_names,
        )
        _extract_calls(
            path=normalised,
            content=decl_scan,
            imported_names=imported_names,
            local_names=local_names,
            result=result,
        )
        if lang == "tsx":
            _extract_jsx_components(
                path=normalised,
                content=decl_scan,
                imported_names=imported_names,
                local_names=local_names,
                result=result,
            )

    # S3: Folder→...→File spine.
    emit_contains_spine(
        file_path=path,
        file_uid_=file_node.uid,
        result=result,
        extractor_id=EXTRACTOR_ID,
    )

    # S3: File→Class / File→Function / File→Interface direct ``contains``
    # edges (ts extractor already wires Module→decl; add File→decl for
    # the SPA tree-view spine). Uniqueness is enforced by the backend.
    for name, decl_uid in local_names.items():
        if (
            decl_uid.startswith("code:class:")
            or decl_uid.startswith("code:function:")
            or decl_uid.startswith("code:interface:")
        ):
            result.edges.append(
                GraphEdge(
                    source_uid=file_node.uid,
                    target_uid=decl_uid,
                    edge_type="contains",
                    extractor=EXTRACTOR_ID,
                    confidence=1.0,
                )
            )

    _promote_stubs(result)
    return result


# ---------------------------------------------------------------------------
# Comment / string stripping
# ---------------------------------------------------------------------------


def _strip_comments(content: str) -> str:
    """Remove comments but leave everything else (strings included).

    Used for import extraction — the module specifier IS a string, so
    we must keep it. Length-preserving substitution keeps line numbers
    and `source_span` offsets accurate.
    """

    def _blk(match: re.Match[str]) -> str:
        return "".join("\n" if c == "\n" else " " for c in match.group(0))

    out = _BLOCK_COMMENT_RE.sub(_blk, content)
    out = _LINE_COMMENT_RE.sub(lambda m: " " * len(m.group(0)), out)
    return out


def _strip_comments_and_strings(content: str) -> str:
    """Remove comments AND blank the interior of string / template literals.

    Used for decl + call-site scanning. Keeping quotes (length-
    preserving) means regexes that look for `foo(` won't match inside
    `'foo(\"x\");'`.
    """

    def _str(match: re.Match[str]) -> str:
        raw = match.group(0)
        if len(raw) < 2:
            return raw
        return raw[0] + " " * (len(raw) - 2) + raw[-1]

    out = _strip_comments(content)
    out = _STRING_RE.sub(_str, out)
    return out


# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------


def _extract_imports(
    *,
    path: str,
    module_uid_: str,
    content: str,
    result: ExtractionResult,
    extractor_override: str | None = None,
) -> dict[str, str]:
    """Emit import nodes + edges and return {local_name -> module specifier}.

    TASK-121: when ``extractor_override`` is set (the caller has
    detected a successful tree-sitter parse and the user has opted in
    via `--extractor=tree-sitter`), every emitted import edge / node
    carries that ID instead of the legacy ``code_ts@v1``.  The regex
    keeps doing the extraction — the overlay parse acts as the
    "is this really TS/TSX?" gate so a successful tag swap means a
    grammar-validated source.
    """
    eid = extractor_override or EXTRACTOR_ID
    eid_signal_named = "tree_sitter_import" if extractor_override else "ts_import"
    eid_signal_side = (
        "tree_sitter_import_side_effect" if extractor_override else "ts_import_side_effect"
    )
    imported_names: dict[str, str] = {}

    for match in _IMPORT_RE.finditer(content):
        clause = match.group("clause")
        module = match.group("module")
        line = content[: match.start()].count("\n") + 1
        target_mod_uid = _resolve_module_uid(path, module)

        for name in _parse_clause(clause):
            # E3: drop {line} from UID so import-shuffle doesn't spawn
            # duplicates. Line still carried in start_line.
            imp_uid = f"code:import:{_normalize_path(path)}::{name}"
            result.nodes.append(
                GraphNode(
                    uid=imp_uid,
                    kind="code:import",
                    label=f"import {name}",
                    file_path=path,
                    start_line=line,
                    lang="ts",
                    metadata={
                        "source_module": module,
                        "imported": name,
                        "extractor": eid,
                    },
                )
            )
            result.edges.append(
                GraphEdge(
                    source_uid=module_uid_,
                    target_uid=imp_uid,
                    edge_type="contains",
                    extractor=eid,
                    confidence=1.0,
                )
            )
            imported_names[name] = module

        result.edges.append(
            GraphEdge(
                source_uid=module_uid_,
                target_uid=target_mod_uid,
                edge_type="imports",
                extractor=eid,
                confidence=0.9,
                source_span=f"{path}:{line}",
                evidence=(EvidenceSignal(eid_signal_named, 0.9),),
            )
        )

    for match in _SIDE_EFFECT_IMPORT_RE.finditer(content):
        module = match.group("module")
        line = content[: match.start()].count("\n") + 1
        target_mod_uid = _resolve_module_uid(path, module)
        result.edges.append(
            GraphEdge(
                source_uid=module_uid_,
                target_uid=target_mod_uid,
                edge_type="imports",
                extractor=eid,
                confidence=0.85,
                source_span=f"{path}:{line}",
                evidence=(EvidenceSignal(eid_signal_side, 0.85),),
            )
        )

    # E7: dynamic imports (lazy routes / code-splitting).
    for match in _DYNAMIC_IMPORT_RE.finditer(content):
        module = match.group("module")
        line = content[: match.start()].count("\n") + 1
        target_mod_uid = _resolve_module_uid(path, module)
        result.edges.append(
            GraphEdge(
                source_uid=module_uid_,
                target_uid=target_mod_uid,
                edge_type="imports",
                extractor=eid,
                confidence=0.7,
                source_span=f"{path}:{line}",
                evidence=(EvidenceSignal("ts_dynamic_import", 0.7),),
            )
        )

    for match in _EXPORT_FROM_RE.finditer(content):
        module = match.group("module")
        line = content[: match.start()].count("\n") + 1
        target_mod_uid = _resolve_module_uid(path, module)
        result.edges.append(
            GraphEdge(
                source_uid=module_uid_,
                target_uid=target_mod_uid,
                edge_type="re_exports",
                extractor=eid,
                confidence=0.9,
                source_span=f"{path}:{line}",
            )
        )

    return imported_names


def _parse_clause(clause: str) -> list[str]:
    clause = clause.strip()
    if clause.startswith("{"):
        inner = clause[1:-1]
        names = []
        for part in inner.split(","):
            name = part.strip()
            if not name:
                continue
            # Drop `as alias` — keep local name.
            if " as " in name:
                name = name.split(" as ")[-1].strip()
            names.append(name)
        return names
    if clause.startswith("*"):
        return [clause.split("as")[-1].strip()]
    return [clause]


def _resolve_module_uid(origin: str, specifier: str) -> str:
    """Resolve an import specifier to a module uid.

    Resolution precedence (matches `tsc --traceResolution`):
      1. Relative paths become repo-rooted file uids.
      2. tsconfig `compilerOptions.paths` aliases (TASK-082) — when an
         active ToolchainContext declares e.g. `@shared/*` →
         `packages/shared/src/*`, expand the wildcard and emit a
         repo-local module uid.
      3. tsconfig `compilerOptions.baseUrl` — non-relative specifiers
         that resolve under baseUrl become repo-local module uids.
      4. Otherwise treat as bare package name (`code:module:npm:...`).
    """
    if specifier.startswith("."):
        origin_dir = PurePosixPath(origin).parent
        candidate = (origin_dir / specifier).as_posix()
        parts: list[str] = []
        for part in candidate.split("/"):
            if part in ("", "."):
                continue
            if part == "..":
                if parts:
                    parts.pop()
                continue
            parts.append(part)
        resolved = "/".join(parts)
        # Add `.ts` if no extension was given so the uid lines up with
        # the actual file node the TS extractor would emit.
        if "." not in PurePosixPath(resolved).name:
            resolved += ".ts"
        return f"code:module:{resolved}"

    # TASK-082: tsconfig.paths / baseUrl aliasing.
    aliased = _resolve_ts_alias(specifier)
    if aliased:
        return f"code:module:{aliased}"

    return f"code:module:npm:{specifier}"


def _resolve_ts_alias(specifier: str) -> str | None:
    """Match `specifier` against the active ToolchainContext's
    tsconfig.paths + baseUrl.  Returns the rewritten POSIX module path
    (without `.ts` suffix appended; caller already handles extension)
    or None when no alias matches.
    """
    try:
        from ..toolchain import get_active
    except ImportError:
        return None
    ctx = get_active()
    if ctx is None:
        return None

    # First-fit alias scan.  Anchored prefix: `@shared/*` matches any
    # specifier starting with `@shared/`.  Exact pattern (no `*`) must
    # equal the specifier.
    for pattern, replacements in ctx.ts_paths.items():
        rewrite = _apply_ts_path(pattern, replacements, specifier)
        if rewrite is not None:
            return rewrite

    # baseUrl path: if the specifier maps onto a file under baseUrl,
    # produce that path.  baseUrl is already repo-relative POSIX.
    if ctx.ts_base_url:
        candidate = f"{ctx.ts_base_url.rstrip('/')}/{specifier}"
        return candidate

    return None


def _apply_ts_path(
    pattern: str,
    replacements: tuple[str, ...],
    specifier: str,
) -> str | None:
    """Implement `tsc`-style `*` substitution for a single paths entry."""
    if "*" in pattern:
        prefix, _, suffix = pattern.partition("*")
        if not specifier.startswith(prefix) or not specifier.endswith(suffix):
            return None
        captured = specifier[len(prefix) : len(specifier) - len(suffix) if suffix else None]
        for repl in replacements:
            if "*" not in repl:
                continue
            return repl.replace("*", captured, 1)
        # No `*` in replacements — use the first as-is.
        return replacements[0] if replacements else None
    if specifier == pattern:
        for repl in replacements:
            return repl
    return None


# ---------------------------------------------------------------------------
# Declarations
# ---------------------------------------------------------------------------


def _extract_classes(
    *,
    path: str,
    module_uid_: str,
    lang: str,
    content: str,
    result: ExtractionResult,
    local_names: dict[str, str],
) -> None:
    for match in _CLASS_RE.finditer(content):
        name = match.group("name")
        line = content[: match.start()].count("\n") + 1
        uid = class_uid(path, name)
        signature = _format_class_signature(
            name=name, parent=match.group("parent"), implements=match.group("implements")
        )
        decorators = _collect_preceding_decorators(content, match.start())
        result.nodes.append(
            GraphNode(
                uid=uid,
                kind="code:class",
                label=name,
                file_path=path,
                start_line=line,
                signature=signature,
                lang=lang,
                metadata={
                    "extractor": EXTRACTOR_ID,
                    "decorators": list(decorators),
                },
            )
        )
        local_names[name] = uid
        result.edges.append(
            GraphEdge(
                source_uid=module_uid_,
                target_uid=uid,
                edge_type="contains",
                extractor=EXTRACTOR_ID,
                confidence=1.0,
                source_span=f"{path}:{line}",
            )
        )
        if match.group("parent"):
            result.edges.append(
                GraphEdge(
                    source_uid=uid,
                    target_uid=f"code:external:{match.group('parent')}",
                    edge_type="inherits_from",
                    extractor=EXTRACTOR_ID,
                    confidence=0.7,
                    evidence=(EvidenceSignal("ts_extends", 0.7),),
                )
            )
        if match.group("implements"):
            for iface in _split_implements(match.group("implements")):
                result.edges.append(
                    GraphEdge(
                        source_uid=uid,
                        target_uid=f"code:external:{iface}",
                        edge_type="implements",
                        extractor=EXTRACTOR_ID,
                        confidence=0.6,
                    )
                )
        for decorator in decorators:
            result.edges.append(
                GraphEdge(
                    source_uid=uid,
                    target_uid=f"code:external:{decorator}",
                    edge_type="is_decorated_by",
                    extractor=EXTRACTOR_ID,
                    confidence=0.7,
                )
            )


def _extract_interfaces(
    *,
    path: str,
    module_uid_: str,
    lang: str,
    content: str,
    result: ExtractionResult,
    local_names: dict[str, str],
) -> None:
    for match in _INTERFACE_RE.finditer(content):
        name = match.group("name")
        line = content[: match.start()].count("\n") + 1
        uid = interface_uid(path, name)
        result.nodes.append(
            GraphNode(
                uid=uid,
                kind="code:interface",
                label=name,
                file_path=path,
                start_line=line,
                lang=lang,
                signature=f"interface {name}",
                metadata={"extractor": EXTRACTOR_ID},
            )
        )
        local_names[name] = uid
        result.edges.append(
            GraphEdge(
                source_uid=module_uid_,
                target_uid=uid,
                edge_type="contains",
                extractor=EXTRACTOR_ID,
                confidence=1.0,
            )
        )
        parents_raw = match.group("parents") or ""
        for parent in _split_implements(parents_raw):
            result.edges.append(
                GraphEdge(
                    source_uid=uid,
                    target_uid=f"code:external:{parent}",
                    edge_type="extends",
                    extractor=EXTRACTOR_ID,
                    confidence=0.7,
                )
            )


def _extract_functions(
    *,
    path: str,
    module_uid_: str,
    lang: str,
    content: str,
    result: ExtractionResult,
    local_names: dict[str, str],
) -> None:
    for match in _FUNCTION_RE.finditer(content):
        name = match.group("name")
        line = content[: match.start()].count("\n") + 1
        uid = function_uid(path, name)
        result.nodes.append(
            GraphNode(
                uid=uid,
                kind="code:function",
                label=name,
                file_path=path,
                start_line=line,
                signature=f"function {name}({match.group('generics') or ''})".replace("()", "(…)"),
                lang=lang,
                metadata={"extractor": EXTRACTOR_ID},
            )
        )
        local_names[name] = uid
        result.edges.append(
            GraphEdge(
                source_uid=module_uid_,
                target_uid=uid,
                edge_type="contains",
                extractor=EXTRACTOR_ID,
                confidence=1.0,
            )
        )


def _extract_arrow_fns(
    *,
    path: str,
    module_uid_: str,
    lang: str,
    content: str,
    result: ExtractionResult,
    local_names: dict[str, str],
) -> None:
    for match in _ARROW_RE.finditer(content):
        name = match.group("name")
        if name in local_names:
            continue
        line = content[: match.start()].count("\n") + 1
        uid = function_uid(path, name)
        result.nodes.append(
            GraphNode(
                uid=uid,
                kind="code:function",
                label=name,
                file_path=path,
                start_line=line,
                signature=f"const {name} = (…) =>",
                lang=lang,
                metadata={"arrow": True, "extractor": EXTRACTOR_ID},
            )
        )
        local_names[name] = uid
        result.edges.append(
            GraphEdge(
                source_uid=module_uid_,
                target_uid=uid,
                edge_type="contains",
                extractor=EXTRACTOR_ID,
                confidence=1.0,
            )
        )


# ---------------------------------------------------------------------------
# Call-sites
# ---------------------------------------------------------------------------


_TS_KEYWORDS = frozenset(
    {
        "if",
        "for",
        "while",
        "switch",
        "return",
        "new",
        "catch",
        "function",
        "typeof",
        "await",
        "import",
        "export",
        "throw",
        "yield",
    }
)


def _extract_calls(
    *,
    path: str,
    content: str,
    imported_names: dict[str, str],
    local_names: dict[str, str],
    result: ExtractionResult,
) -> None:
    """Emit call / constructs edges sourced at the module level.

    Per plan §7.2 the baseline scanner records call-sites against the
    enclosing module (not the function) because regex alone cannot
    reliably determine function boundaries. The LSP overlay re-homes
    these edges to the exact caller.
    """
    module = module_uid(path)
    for match in _CALL_RE.finditer(content):
        target = match.group("target")
        root = target.split(".")[0]
        if root in _TS_KEYWORDS:
            continue
        line = content[: match.start()].count("\n") + 1
        is_ctor = target.split(".")[-1][:1].isupper()

        if target in local_names:
            resolved = local_names[target]
            confidence = 0.5
            signal = EvidenceSignal("same_scope", 0.5)
        elif root in imported_names:
            specifier = imported_names[root]
            tail = ".".join(target.split(".")[1:]) or root
            resolved = f"code:external:{specifier}:{tail}"
            confidence = 0.4
            signal = EvidenceSignal("explicit_import", 0.4, note=specifier)
        else:
            resolved = f"code:external:unresolved:{target}"
            confidence = 0.3
            signal = EvidenceSignal("unresolved_call", 0.3)

        result.edges.append(
            GraphEdge(
                source_uid=module,
                target_uid=resolved,
                edge_type="constructs" if is_ctor else "calls",
                extractor=EXTRACTOR_ID,
                confidence=confidence,
                source_span=f"{path}:{line}",
                evidence=(signal,),
            )
        )


def _extract_jsx_components(
    *,
    path: str,
    content: str,
    imported_names: dict[str, str],
    local_names: dict[str, str],
    result: ExtractionResult,
) -> None:
    module = module_uid(path)
    seen: set[str] = set()
    for match in _JSX_COMPONENT_RE.finditer(content):
        name = match.group("name")
        if name in seen:
            continue
        seen.add(name)
        line = content[: match.start()].count("\n") + 1
        if name in local_names:
            resolved = local_names[name]
            confidence = 0.8
        elif name in imported_names:
            resolved = f"code:external:{imported_names[name]}:{name}"
            confidence = 0.7
        else:
            resolved = f"code:external:unresolved:{name}"
            confidence = 0.4
        result.edges.append(
            GraphEdge(
                source_uid=module,
                target_uid=resolved,
                edge_type="constructs",
                extractor=EXTRACTOR_ID,
                confidence=confidence,
                source_span=f"{path}:{line}",
                evidence=(EvidenceSignal("jsx_component", 0.8),),
            )
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _collect_preceding_decorators(content: str, idx: int) -> tuple[str, ...]:
    """Walk backwards from `idx` and return decorators attached to the decl."""
    # Scan at most 5 lines upward.
    upper = max(content.rfind("\n", 0, idx), 0)
    # Find the start of that line.
    line_start = content.rfind("\n", 0, upper)
    line_start = line_start + 1 if line_start >= 0 else 0
    block = content[line_start:idx]
    decorators: list[str] = []
    for match in _DECORATOR_RE.finditer(block):
        decorators.append(match.group("target"))
    return tuple(decorators)


def _format_class_signature(*, name: str, parent: str | None, implements: str | None) -> str:
    parts = [f"class {name}"]
    if parent:
        parts.append(f"extends {parent}")
    if implements:
        ifaces = ", ".join(_split_implements(implements))
        if ifaces:
            parts.append(f"implements {ifaces}")
    return " ".join(parts)


def _count_ts_nodes(root) -> int:
    """Count AST nodes for tree-sitter overlay health-check metric."""
    if root is None:
        return 0
    stack = [root]
    total = 0
    while stack:
        node = stack.pop()
        total += 1
        stack.extend(node.children)
    return total


def _split_implements(raw: str) -> list[str]:
    raw = raw.strip()
    if not raw:
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


__all__ = [
    "EXTRACTOR_ID",
    "class_uid",
    "extract",
    "file_uid",
    "function_uid",
    "interface_uid",
    "module_uid",
]
