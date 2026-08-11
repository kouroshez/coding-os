"""code_generic — the hand-written rust and ruby edge hooks.

Rust and ruby ship with grammars and got bespoke walkers before the table-driven
path existed; their idioms (a bare ruby identifier that is really a call, a rust
`impl Trait for Type`) do not reduce to the shared handler shape, so they stay
hand-written. Confidence tiers match the table-driven hooks: 0.9 same-file
AST-resolved, 0.5 cross-file linkable stub, 0.3 dynamic dispatch.
"""

from __future__ import annotations

from typing import Any

from ._generic_nodes import _edge, _ext_uid, _ext_unresolved_uid, _node_name, _node_text
from .md_links import ExtractionResult


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
                        _edge(
                            result, cur_func or file_uid, _ext_unresolved_uid(cname), "calls", 0.3
                        )
                    elif cname in func_index:
                        _edge(result, cur_func or file_uid, func_index[cname], "calls", 0.9)
                    else:
                        _edge(result, cur_func or file_uid, _ext_uid(cname), "calls", 0.5)
        for c in node.children:
            walk(c, cur_func, cur_class)

    walk(root, None, None)
