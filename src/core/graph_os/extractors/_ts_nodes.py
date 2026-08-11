"""tree-sitter node and type primitives for the TypeScript / TSX walker.

Pure readers over a parsed tree — name/line/type-head extraction, callee
reduction, JSX detection, enclosing-scope resolution. They own no state and
emit no nodes, so the declaration and call walkers share them freely.
"""

from __future__ import annotations

from typing import Any

from ._ts_uids import EXTRACTOR_ID_TS, _ts_method_uid, class_uid, function_uid


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


def _ts_has_jsx(node: Any) -> bool:
    """True when the subtree contains a JSX element — marks React components."""
    stack = [node]
    while stack:
        n = stack.pop()
        if n.type in ("jsx_element", "jsx_self_closing_element", "jsx_fragment"):
            return True
        stack.extend(n.children)
    return False


def _ts_component_meta(name: str, body_node: Any, lang: str) -> dict[str, Any]:
    """Metadata for a function/arrow node — flags React components.

    A PascalCase function returning JSX (in a .tsx/.jsx file) is a React
    component; the flag makes "list components" queryable without a new
    node kind (Rule 22 — reuse the existing code:function node).
    """
    meta: dict[str, Any] = {"extractor": EXTRACTOR_ID_TS}
    if lang == "tsx" and name[:1].isupper() and _ts_has_jsx(body_node):
        meta["component"] = True
    return meta


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
                "class_declaration",
                "abstract_class_declaration",
                "class",
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
    if (
        tname
        and tname[:1].isalpha()
        and tname not in ("void", "any", "unknown", "never", "Promise")
    ):
        pending.append((owner_uid, tname, "returns_type", _ts_line(fn_node)))


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
