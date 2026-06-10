"""code_generic — table-driven baseline extractor for polyglot languages.

One extractor covers every language whose tree-sitter grammar is installed
AND whose function / class node-types appear in ``_LANG_SPEC``. It emits the
baseline that makes ``cos_graph_search`` / ``_similar`` / ``_context`` work
for a new language: the file node, the folder ``contains`` spine, and one
node per top-level/nested function- and class-like symbol with ``contains``
edges. Calls / imports / type edges are deliberately left to per-language
extractors — this is the floor, not the ceiling.

Coverage is the curated ``_LANG_SPEC`` set (rust + ruby ship with grammars;
java / c / cpp / c_sharp are code-ready, install the grammar to activate).
Adding a language = one ``_LANG_SPEC`` row + one overlay loader + the
``_EXT_MAP`` route, never a new extractor. Fail-open: a missing grammar or
unsupported extension records a parse error (surfaced by cos_graph_doctor,
TASK-293) and emits just the file node — never raises.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import PurePosixPath
from typing import Any

from ..types import GraphEdge, GraphNode
from .md_links import (
    ExtractionResult,
    ParseError,
    _normalize_path,
    _promote_stubs,
    emit_contains_spine,
)

try:
    from .. import tree_sitter_overlay as _ts_overlay

    _TS_AVAILABLE = _ts_overlay.is_available()
except ImportError:  # pragma: no cover - tree-sitter core absent
    _ts_overlay = None  # type: ignore[assignment]
    _TS_AVAILABLE = False

logger = logging.getLogger("graph_os.extractors.code_generic")
EXTRACTOR_ID = "code_generic@v1"

# Extension → overlay language id. Several extensions map to one grammar
# (.cc/.cpp/.hpp → cpp). The grammar must be registered in
# tree_sitter_overlay._LOADERS for the language to actually parse.
EXT_TO_LANG: dict[str, str] = {
    ".rs": "rust",
    ".rb": "ruby",
    ".java": "java",
    ".c": "c",
    ".h": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".hh": "cpp",
    ".cs": "c_sharp",
    ".scala": "scala",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".lua": "lua",
}

# Per-language tree-sitter node types that denote a function-like or
# class-like definition. Curated (not heuristic) so coverage is honest and
# reliable — ruby names methods `method`, rust uses `function_item`, etc.
_LANG_SPEC: dict[str, dict[str, frozenset[str]]] = {
    "rust": {
        # impl_item is intentionally excluded — it duplicates the struct/enum
        # name as a phantom class. Methods inside an impl are still captured
        # (they attach to the file); linking impl→type is per-language work.
        "func": frozenset({"function_item", "function_signature_item"}),
        "class": frozenset({"struct_item", "enum_item", "trait_item", "mod_item"}),
    },
    "ruby": {
        "func": frozenset({"method", "singleton_method"}),
        "class": frozenset({"class", "module"}),
    },
    "java": {
        "func": frozenset({"method_declaration", "constructor_declaration"}),
        "class": frozenset(
            {
                "class_declaration",
                "interface_declaration",
                "enum_declaration",
                "record_declaration",
                "annotation_type_declaration",
            }
        ),
    },
    "c": {
        "func": frozenset({"function_definition"}),
        "class": frozenset({"struct_specifier", "union_specifier", "enum_specifier"}),
    },
    "cpp": {
        "func": frozenset({"function_definition"}),
        "class": frozenset(
            {"class_specifier", "struct_specifier", "union_specifier", "enum_specifier"}
        ),
    },
    "c_sharp": {
        "func": frozenset(
            {"method_declaration", "constructor_declaration", "local_function_statement"}
        ),
        "class": frozenset(
            {
                "class_declaration",
                "interface_declaration",
                "struct_declaration",
                "enum_declaration",
                "record_declaration",
            }
        ),
    },
    "scala": {
        "func": frozenset({"function_definition"}),
        "class": frozenset({"class_definition", "object_definition", "trait_definition"}),
    },
    "kotlin": {
        "func": frozenset({"function_declaration"}),
        "class": frozenset({"class_declaration", "object_declaration"}),
    },
    "lua": {
        # Lua has no classes — functions only (tables are runtime constructs).
        "func": frozenset({"function_declaration"}),
        "class": frozenset(),
    },
}

_NAME_NODE_TYPES = ("identifier", "type_identifier", "constant", "name", "field_identifier")


def file_uid(path: str) -> str:
    return f"code:file:{_normalize_path(path)}"


def _node_text(node: Any, content_bytes: bytes) -> str:
    try:
        return content_bytes[node.start_byte : node.end_byte].decode("utf-8", errors="replace")
    except Exception:
        return ""


_DECLARATOR_NAME_TYPES = (
    "identifier",
    "field_identifier",
    "type_identifier",
    "qualified_identifier",
    "destructor_name",
    "operator_name",
)


def _name_via_declarator(node: Any, content_bytes: bytes) -> str:
    # C / C++ keep the function name inside a nested `declarator` chain
    # (function_definition → function_declarator → identifier), NOT a `name`
    # field. Descend the declarator field to the leaf identifier so we get
    # `main`, not the return type `int`.
    cur = node
    for _ in range(6):
        nxt = cur.child_by_field_name("declarator")
        if nxt is None:
            break
        cur = nxt
    if cur is not None and cur.type in _DECLARATOR_NAME_TYPES:
        return _node_text(cur, content_bytes).strip()
    return ""


def _node_name(node: Any, content_bytes: bytes) -> str:
    # Most grammars expose the symbol name as the "name" field.
    named = node.child_by_field_name("name")
    if named is not None:
        text = _node_text(named, content_bytes).strip()
        if text:
            return text
    # C / C++ : name lives inside the declarator subtree, not a field.
    via_decl = _name_via_declarator(node, content_bytes)
    if via_decl:
        return via_decl
    # Rust impl_item carries the type under "type" instead of a name.
    typ = node.child_by_field_name("type")
    if typ is not None:
        text = _node_text(typ, content_bytes).strip()
        if text:
            return text
    for child in node.children:
        if child.type in _NAME_NODE_TYPES:
            text = _node_text(child, content_bytes).strip()
            if text:
                return text
    return ""


def _unique_uid(kind: str, normalised: str, name: str, seen: set[str]) -> str:
    base = f"{kind}:{normalised}::{name}"
    uid = base
    n = 2
    # Deterministic disambiguation for same-named siblings (traversal order
    # is stable for identical content, so the suffix is stable across runs).
    while uid in seen:
        uid = f"{base}#{n}"
        n += 1
    seen.add(uid)
    return uid


def _walk(
    node: Any,
    *,
    parent_uid: str,
    spec: dict[str, frozenset[str]],
    normalised: str,
    lang: str,
    content_bytes: bytes,
    result: ExtractionResult,
    seen: set[str],
) -> None:
    for child in node.children:
        kind: str | None = None
        if child.type in spec["func"]:
            kind = "code:function"
        elif child.type in spec["class"]:
            kind = "code:class"

        if kind is not None:
            name = _node_name(child, content_bytes)
            if name:
                uid = _unique_uid(kind, normalised, name, seen)
                result.nodes.append(
                    GraphNode(
                        uid=uid,
                        kind=kind,
                        label=name,
                        file_path=normalised,
                        start_line=child.start_point[0] + 1,
                        lang=lang,
                        metadata={"extractor": EXTRACTOR_ID, "ts_type": child.type},
                    )
                )
                result.edges.append(
                    GraphEdge(
                        source_uid=parent_uid,
                        target_uid=uid,
                        edge_type="contains",
                        extractor=EXTRACTOR_ID,
                        confidence=1.0,
                    )
                )
                # Descend with this symbol as parent so methods nest under
                # their class (file → class → method).
                _walk(
                    child,
                    parent_uid=uid,
                    spec=spec,
                    normalised=normalised,
                    lang=lang,
                    content_bytes=content_bytes,
                    result=result,
                    seen=seen,
                )
                continue

        _walk(
            child,
            parent_uid=parent_uid,
            spec=spec,
            normalised=normalised,
            lang=lang,
            content_bytes=content_bytes,
            result=result,
            seen=seen,
        )


# ---------------------------------------------------------------------------
# Per-language edge extraction (calls / imports / inherits) — TASK-305.
# The node walk gives the baseline (file+spine+function/class+contains); these
# hooks graduate a language to Go-grade relationship edges. Targets not
# resolvable in-file point at code:external:<name> stubs so the post-walk link
# pass can resolve them cross-file; genuinely-dynamic dispatch stays
# code:external:unresolved:<name> at low confidence. Decision (TASK-305): keep
# this in code_generic as per-language hooks rather than spinning up full
# code_rust/code_ruby modules — the node baseline is shared, only the edge
# grammar differs, so one module with a dispatch table is the smaller surface.
# ---------------------------------------------------------------------------


def _ext_uid(name: str) -> str:
    return f"code:external:{name}"


def _ext_unresolved_uid(name: str) -> str:
    return f"code:external:unresolved:{name}"


def _edge(result: ExtractionResult, src: str, tgt: str, kind: str, conf: float) -> None:
    result.edges.append(
        GraphEdge(
            source_uid=src,
            target_uid=tgt,
            edge_type=kind,
            extractor=EXTRACTOR_ID,
            confidence=conf,
        )
    )


def _rust_use_path(node: Any, cb: bytes) -> str:
    for c in node.children:
        if c.type in (
            "scoped_identifier",
            "identifier",
            "use_list",
            "scoped_use_list",
            "use_wildcard",
            "use_as_clause",
        ):
            return _node_text(c, cb).strip().rstrip(";").replace(" ", "")
    return ""


def _rust_call_target(node: Any, cb: bytes, func_index: dict[str, str]) -> tuple[str | None, float]:
    fn = node.child_by_field_name("function")
    if fn is None:
        return None, 0.0
    if fn.type == "identifier":
        name = _node_text(fn, cb).strip()
        if name in func_index:
            return func_index[name], 0.9  # same-file, AST-direct
        return _ext_uid(name), 0.5  # cross-file, linkable
    if fn.type == "scoped_identifier":
        return _ext_uid(_node_text(fn, cb).strip().split("::")[-1]), 0.5
    if fn.type == "field_expression":
        fld = fn.child_by_field_name("field")
        if fld is not None:
            return _ext_unresolved_uid(_node_text(fld, cb).strip()), 0.3  # dynamic dispatch
    return None, 0.0


def _rust_edges(
    root: Any,
    cb: bytes,
    file_uid: str,
    func_index: dict[str, str],
    class_index: dict[str, str],
    result: ExtractionResult,
) -> None:
    def walk(node: Any, cur_func: str | None) -> None:
        nt = node.type
        if nt == "use_declaration":
            path = _rust_use_path(node, cb)
            if path:
                _edge(result, file_uid, _ext_uid(path), "imports", 1.0)
        elif nt == "function_item":
            name = _node_name(node, cb)
            cur_func = func_index.get(name, cur_func)
        elif nt == "impl_item":
            tids = [c for c in node.children if c.type == "type_identifier"]
            if any(c.type == "for" for c in node.children) and len(tids) >= 2:
                trait_name = _node_text(tids[0], cb).strip()
                type_name = _node_text(tids[1], cb).strip()
                _edge(
                    result,
                    class_index.get(type_name, _ext_uid(type_name)),
                    class_index.get(trait_name, _ext_uid(trait_name)),
                    "implements",
                    1.0,
                )
        elif nt == "call_expression":
            tgt, conf = _rust_call_target(node, cb, func_index)
            if tgt:
                _edge(result, cur_func or file_uid, tgt, "calls", conf)
        for c in node.children:
            walk(c, cur_func)

    walk(root, None)


_RUBY_NONCALL = {
    "require",
    "require_relative",
    "include",
    "extend",
    "prepend",
    "attr_accessor",
    "attr_reader",
    "attr_writer",
    "private",
    "public",
    "protected",
}


def _ruby_arg(node: Any, cb: bytes, want: str) -> str:
    for c in node.children:
        if c.type == "argument_list":
            for a in c.children:
                if a.type == want:
                    return _node_text(a, cb).strip().strip("\"'")
    return ""


def _ruby_call_name(node: Any, cb: bytes) -> str:
    m = node.child_by_field_name("method")
    if m is not None:
        return _node_text(m, cb).strip()
    idents = [c for c in node.children if c.type in ("identifier", "constant")]
    return _node_text(idents[-1], cb).strip() if idents else ""


def _ruby_edges(
    root: Any,
    cb: bytes,
    file_uid: str,
    func_index: dict[str, str],
    class_index: dict[str, str],
    result: ExtractionResult,
) -> None:
    def walk(node: Any, cur_func: str | None, cur_class: str | None) -> None:
        nt = node.type
        if nt == "identifier" and cur_func:
            # Ruby idiom: a bare `helper` statement (no parens, no receiver)
            # parses as a plain identifier, not a `call` node. When it stands
            # alone as a statement AND matches a known same-file method, it is
            # almost certainly a call — emit at 0.7 (heuristic tier: a local
            # variable shadowing the method name would fool this, so it stays
            # below the 0.9 AST-certain band).
            parent = node.parent
            name = _node_text(node, cb).strip()
            if (
                parent is not None
                and parent.type in ("body_statement", "then", "else", "begin_block", "do_block")
                and name in func_index
            ):
                _edge(result, cur_func, func_index[name], "calls", 0.7)
        if nt in ("method", "singleton_method"):
            cur_func = func_index.get(_node_name(node, cb), cur_func)
        elif nt in ("class", "module"):
            name = _node_name(node, cb)
            cur_class = class_index.get(name, cur_class)
            sup = node.child_by_field_name("superclass")
            if sup is not None:
                const = next(
                    (c for c in sup.children if c.type in ("constant", "scope_resolution")), None
                )
                sname = _node_text(const, cb).strip() if const is not None else ""
                if sname:
                    _edge(
                        result,
                        cur_class or _ext_uid(name),
                        class_index.get(sname, _ext_uid(sname)),
                        "inherits",
                        1.0,
                    )
        elif nt == "call":
            first = node.children[0] if node.children else None
            head = _node_text(first, cb).strip() if first is not None else ""
            if head in ("require", "require_relative"):
                arg = _ruby_arg(node, cb, "string")
                if arg:
                    _edge(result, file_uid, _ext_uid(arg), "imports", 1.0)
            elif head in ("include", "extend", "prepend"):
                mod = _ruby_arg(node, cb, "constant")
                if mod:
                    _edge(
                        result,
                        cur_class or file_uid,
                        class_index.get(mod, _ext_uid(mod)),
                        "includes",
                        1.0,
                    )
            else:
                cname = _ruby_call_name(node, cb)
                if cname and cname not in _RUBY_NONCALL:
                    if node.child_by_field_name("receiver") is not None:
                        _edge(result, cur_func or file_uid, _ext_unresolved_uid(cname), "calls", 0.3)
                    elif cname in func_index:
                        _edge(result, cur_func or file_uid, func_index[cname], "calls", 0.9)
                    else:
                        _edge(result, cur_func or file_uid, _ext_uid(cname), "calls", 0.5)
        for c in node.children:
            walk(c, cur_func, cur_class)

    walk(root, None, None)


# ---------------------------------------------------------------------------
# Table-driven edge hooks for the remaining 7 languages (TASK-313). One shared
# walker (`_make_spec_edges`) + per-language handler functions — node types
# and field names below were probed live against the installed grammars, not
# guessed. Same confidence tiers as rust/ruby: 0.9 same-file AST-resolved ·
# 0.5 cross-file linkable stub · 0.3 dynamic dispatch.
# ---------------------------------------------------------------------------


def _rightmost_name(node: Any, cb: bytes) -> str:
    cur = node
    while cur.children:
        named = [c for c in cur.children if c.type in _DECLARATOR_NAME_TYPES or c.children]
        if not named:
            break
        cur = named[-1]
    return _node_text(cur, cb).strip()


def _emit_call(
    result: ExtractionResult,
    src_uid: str,
    fn_node: Any,
    cb: bytes,
    func_index: dict[str, str],
    *,
    member_types: tuple[str, ...],
    member_name_field: str | None = None,
) -> None:
    if fn_node is None:
        return
    if fn_node.type == "identifier":
        name = _node_text(fn_node, cb).strip()
        if not name:
            return
        if name in func_index:
            _edge(result, src_uid, func_index[name], "calls", 0.9)
        else:
            _edge(result, src_uid, _ext_uid(name), "calls", 0.5)
        return
    if fn_node.type in member_types:
        if member_name_field:
            named = fn_node.child_by_field_name(member_name_field)
            name = _node_text(named, cb).strip() if named is not None else ""
        else:
            name = _rightmost_name(fn_node, cb)
        if name:
            _edge(result, src_uid, _ext_unresolved_uid(name), "calls", 0.3)


def _first_child_of_type(node: Any, types: tuple[str, ...]) -> Any | None:
    for c in node.children:
        if c.type in types:
            return c
    return None


def _java_handler(node: Any, cb: bytes, ctx: dict[str, Any], result: ExtractionResult) -> None:
    nt = node.type
    if nt == "import_declaration":
        tgt = _first_child_of_type(node, ("scoped_identifier", "identifier"))
        if tgt is not None:
            _edge(result, ctx["file_uid"], _ext_uid(_node_text(tgt, cb).strip()), "imports", 1.0)
    elif nt == "method_invocation":
        named = node.child_by_field_name("name")
        name = _node_text(named, cb).strip() if named is not None else ""
        if not name:
            return
        src = ctx["cur_func"] or ctx["file_uid"]
        if node.child_by_field_name("object") is not None:
            _edge(result, src, _ext_unresolved_uid(name), "calls", 0.3)
        elif name in ctx["func_index"]:
            _edge(result, src, ctx["func_index"][name], "calls", 0.9)
        else:
            _edge(result, src, _ext_uid(name), "calls", 0.5)
    elif nt == "superclass":
        tgt = _first_child_of_type(node, ("type_identifier", "generic_type"))
        if tgt is not None:
            sname = _node_text(tgt, cb).strip().split("<")[0]
            _edge(
                result,
                ctx["cur_class"] or ctx["file_uid"],
                ctx["class_index"].get(sname, _ext_uid(sname)),
                "inherits",
                1.0,
            )
    elif nt == "super_interfaces":
        tl = _first_child_of_type(node, ("type_list",))
        if tl is not None:
            for iname in _node_text(tl, cb).split(","):
                iname = iname.strip().split("<")[0]
                if iname:
                    _edge(
                        result,
                        ctx["cur_class"] or ctx["file_uid"],
                        ctx["class_index"].get(iname, _ext_uid(iname)),
                        "implements",
                        1.0,
                    )


def _c_handler(node: Any, cb: bytes, ctx: dict[str, Any], result: ExtractionResult) -> None:
    nt = node.type
    if nt == "preproc_include":
        path = node.child_by_field_name("path")
        if path is not None:
            header = _node_text(path, cb).strip().strip('"<>')
            if header:
                _edge(result, ctx["file_uid"], _ext_uid(header), "imports", 1.0)
    elif nt == "call_expression":
        _emit_call(
            result,
            ctx["cur_func"] or ctx["file_uid"],
            node.child_by_field_name("function"),
            cb,
            ctx["func_index"],
            member_types=("field_expression",),
            member_name_field="field",
        )
    elif nt == "base_class_clause":  # cpp only; absent in plain c ASTs
        for c in node.children:
            if c.type in ("type_identifier", "qualified_identifier", "template_type"):
                bname = _node_text(c, cb).strip().split("<")[0]
                if bname:
                    _edge(
                        result,
                        ctx["cur_class"] or ctx["file_uid"],
                        ctx["class_index"].get(bname, _ext_uid(bname)),
                        "inherits",
                        1.0,
                    )


def _csharp_handler(node: Any, cb: bytes, ctx: dict[str, Any], result: ExtractionResult) -> None:
    nt = node.type
    if nt == "using_directive":
        tgt = _first_child_of_type(node, ("qualified_name", "identifier"))
        if tgt is not None:
            _edge(result, ctx["file_uid"], _ext_uid(_node_text(tgt, cb).strip()), "imports", 1.0)
    elif nt == "invocation_expression":
        _emit_call(
            result,
            ctx["cur_func"] or ctx["file_uid"],
            node.child_by_field_name("function"),
            cb,
            ctx["func_index"],
            member_types=("member_access_expression",),
            member_name_field="name",
        )
    elif nt == "base_list":
        # C# cannot statically distinguish base class from interface in the
        # base_list — emit `inherits` for each at 0.9 (honest, not inflated).
        for c in node.children:
            if c.type in ("identifier", "qualified_name", "generic_name"):
                bname = _node_text(c, cb).strip().split("<")[0]
                if bname:
                    _edge(
                        result,
                        ctx["cur_class"] or ctx["file_uid"],
                        ctx["class_index"].get(bname, _ext_uid(bname)),
                        "inherits",
                        0.9,
                    )


def _scala_handler(node: Any, cb: bytes, ctx: dict[str, Any], result: ExtractionResult) -> None:
    nt = node.type
    if nt == "import_declaration":
        path = "".join(
            _node_text(c, cb)
            for i, c in enumerate(node.children)
            if node.field_name_for_child(i) == "path"
        ).strip()
        if path:
            _edge(result, ctx["file_uid"], _ext_uid(path), "imports", 1.0)
    elif nt == "call_expression":
        _emit_call(
            result,
            ctx["cur_func"] or ctx["file_uid"],
            node.child_by_field_name("function"),
            cb,
            ctx["func_index"],
            member_types=("field_expression",),
            member_name_field="field",
        )
    elif nt == "extends_clause":
        # First type ⇒ inherits; subsequent `with` types ⇒ includes (mixins).
        first = True
        for c in node.children:
            if c.type in ("type_identifier", "generic_type"):
                bname = _node_text(c, cb).strip().split("[")[0]
                if not bname:
                    continue
                kind = "inherits" if first else "includes"
                first = False
                _edge(
                    result,
                    ctx["cur_class"] or ctx["file_uid"],
                    ctx["class_index"].get(bname, _ext_uid(bname)),
                    kind,
                    1.0,
                )


def _kotlin_handler(node: Any, cb: bytes, ctx: dict[str, Any], result: ExtractionResult) -> None:
    nt = node.type
    if nt == "import":
        tgt = _first_child_of_type(node, ("qualified_identifier", "identifier"))
        if tgt is not None:
            _edge(result, ctx["file_uid"], _ext_uid(_node_text(tgt, cb).strip()), "imports", 1.0)
    elif nt == "call_expression":
        # kotlin call_expression has no named fields: child[0] is the callee.
        head = node.children[0] if node.children else None
        if head is None:
            return
        src = ctx["cur_func"] or ctx["file_uid"]
        if head.type == "identifier":
            name = _node_text(head, cb).strip()
            if not name:
                return
            if name in ctx["func_index"]:
                _edge(result, src, ctx["func_index"][name], "calls", 0.9)
            else:
                _edge(result, src, _ext_uid(name), "calls", 0.5)
        elif head.type == "navigation_expression":
            name = _rightmost_name(head, cb)
            if name:
                _edge(result, src, _ext_unresolved_uid(name), "calls", 0.3)
    elif nt == "delegation_specifier":
        ci = _first_child_of_type(node, ("constructor_invocation",))
        if ci is not None:
            ut = _first_child_of_type(ci, ("user_type",))
            bname = _node_text(ut, cb).strip().split("<")[0] if ut is not None else ""
            if bname:
                _edge(
                    result,
                    ctx["cur_class"] or ctx["file_uid"],
                    ctx["class_index"].get(bname, _ext_uid(bname)),
                    "inherits",
                    1.0,
                )
        else:
            ut = _first_child_of_type(node, ("user_type",))
            if ut is not None:
                iname = _node_text(ut, cb).strip().split("<")[0]
                if iname:
                    _edge(
                        result,
                        ctx["cur_class"] or ctx["file_uid"],
                        ctx["class_index"].get(iname, _ext_uid(iname)),
                        "implements",
                        1.0,
                    )


def _lua_handler(node: Any, cb: bytes, ctx: dict[str, Any], result: ExtractionResult) -> None:
    if node.type != "function_call":
        return
    named = node.child_by_field_name("name")
    if named is None:
        return
    src = ctx["cur_func"] or ctx["file_uid"]
    if named.type == "identifier":
        name = _node_text(named, cb).strip()
        if not name:
            return
        if name == "require":
            args = node.child_by_field_name("arguments")
            mod = ""
            if args is not None:
                s = _first_child_of_type(args, ("string",))
                mod = _node_text(s, cb).strip().strip("\"'") if s is not None else ""
            if mod:
                _edge(result, ctx["file_uid"], _ext_uid(mod), "imports", 1.0)
            return
        if name in ctx["func_index"]:
            _edge(result, src, ctx["func_index"][name], "calls", 0.9)
        else:
            _edge(result, src, _ext_uid(name), "calls", 0.5)
    elif named.type in ("dot_index_expression", "method_index_expression"):
        name = _rightmost_name(named, cb)
        if name:
            _edge(result, src, _ext_unresolved_uid(name), "calls", 0.3)


_SPEC_HANDLERS: dict[str, Any] = {
    "java": _java_handler,
    "c": _c_handler,
    "cpp": _c_handler,  # superset: base_class_clause only appears in cpp ASTs
    "c_sharp": _csharp_handler,
    "scala": _scala_handler,
    "kotlin": _kotlin_handler,
    "lua": _lua_handler,
}


def _make_spec_edges(lang: str):
    handler = _SPEC_HANDLERS[lang]
    spec = _LANG_SPEC[lang]

    def edges(
        root: Any,
        cb: bytes,
        file_uid: str,
        func_index: dict[str, str],
        class_index: dict[str, str],
        result: ExtractionResult,
    ) -> None:
        ctx: dict[str, Any] = {
            "file_uid": file_uid,
            "func_index": func_index,
            "class_index": class_index,
            "cur_func": None,
            "cur_class": None,
        }

        def walk(node: Any, cur_func: str | None, cur_class: str | None) -> None:
            nt = node.type
            if nt in spec["func"]:
                cur_func = func_index.get(_node_name(node, cb), cur_func)
            elif nt in spec["class"]:
                cur_class = class_index.get(_node_name(node, cb), cur_class)
            ctx["cur_func"] = cur_func
            ctx["cur_class"] = cur_class
            handler(node, cb, ctx, result)
            for c in node.children:
                walk(c, cur_func, cur_class)

        walk(root, None, None)

    return edges


_LANG_EDGES = {
    "rust": _rust_edges,
    "ruby": _ruby_edges,
    **{lang: _make_spec_edges(lang) for lang in _SPEC_HANDLERS},
}


def extract(path: str, content: str) -> ExtractionResult:
    """Parse a polyglot source file → file + folder spine + symbol nodes."""
    result = ExtractionResult()
    normalised = _normalize_path(path)
    suffix = PurePosixPath(normalised).suffix.lower()
    lang = EXT_TO_LANG.get(suffix)
    file_uid_str = file_uid(path)
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]

    # File node + folder spine first, so the file is in the graph even when
    # the grammar is missing (its symbols just won't be).
    result.nodes.append(
        GraphNode(
            uid=file_uid_str,
            kind="code:file",
            label=PurePosixPath(normalised).name,
            file_path=normalised,
            lang=lang or "",
            content_hash=content_hash,
            metadata={"extractor": EXTRACTOR_ID},
        )
    )
    emit_contains_spine(
        file_path=path,
        file_uid_=file_uid_str,
        result=result,
        extractor_id=EXTRACTOR_ID,
    )

    spec = _LANG_SPEC.get(lang) if lang else None
    if spec is None:
        result.parse_errors.append(
            ParseError(kind="lang_unsupported", detail=f"no generic spec for {suffix or path}")
        )
        return result
    if not _TS_AVAILABLE or _ts_overlay is None:
        result.parse_errors.append(ParseError(kind="dep_missing", detail="tree-sitter core absent"))
        return result

    parsed = _ts_overlay.parse(lang, content)
    if parsed is None:
        result.parse_errors.append(
            ParseError(kind="dep_missing", detail=f"grammar '{lang}' not installed")
        )
        return result

    content_bytes = content.encode("utf-8")
    seen: set[str] = {file_uid_str}
    _walk(
        parsed.root,
        parent_uid=file_uid_str,
        spec=spec,
        normalised=normalised,
        lang=lang,
        content_bytes=content_bytes,
        result=result,
        seen=seen,
    )

    # Per-language relationship edges (calls / imports / inherits) on top of
    # the baseline node walk. func/class indexes let same-file calls resolve
    # to real uids; everything else points at a code:external stub that the
    # post-walk link pass resolves cross-file (TASK-305).
    edge_hook = _LANG_EDGES.get(lang)
    if edge_hook is not None:
        func_index = {n.label: n.uid for n in result.nodes if n.kind == "code:function"}
        class_index = {n.label: n.uid for n in result.nodes if n.kind == "code:class"}
        try:
            edge_hook(parsed.root, content_bytes, file_uid_str, func_index, class_index, result)
        except Exception as exc:  # fail-open — baseline nodes already emitted
            logger.debug("edge hook failed for %s: %s", normalised, exc)
        _promote_stubs(result)

    err_count = sum(1 for _ in _ts_overlay.iter_nodes(parsed.root, {"ERROR"}))
    if err_count:
        result.parse_errors.append(
            ParseError(kind="tree_sitter_error", detail=f"{err_count} ERROR node(s)")
        )
    return result


__all__ = ["EXTRACTOR_ID", "EXT_TO_LANG", "extract", "file_uid"]
