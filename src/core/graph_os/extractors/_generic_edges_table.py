"""code_generic — the table-driven edge hooks for the remaining 7 languages.

One shared walker (`_make_spec_edges`) drives a per-language handler that maps
the grammar's import / call / inheritance node types onto graph edges. Node
types and field names were probed live against the installed grammars, not
guessed. Same confidence tiers as the hand-written rust/ruby hooks.
"""

from __future__ import annotations

from typing import Any

from ._generic_nodes import _edge, _ext_uid, _ext_unresolved_uid, _node_name, _node_text
from ._generic_spec import _DECLARATOR_NAME_TYPES, _LANG_SPEC
from .md_links import ExtractionResult


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
