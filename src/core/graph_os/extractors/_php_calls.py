"""graph_os — PHP same-file call + construction edges (Python `same_scope` parity).

Resolves bare `f()`, `$this->m()`, `self::m()`, `static::m()`, `Class::m()` and
`new X()` against declarations found in the same file. Imports only the
`_php_uids` leaf, never a walker sibling.
"""

from __future__ import annotations

from typing import Any

from ..types import EvidenceSignal, GraphEdge
from ._php_uids import (
    EXTRACTOR_ID,
    _find_field,
    _node_text,
    _php_short,
    _resolve_php_type,
    class_uid,
    func_uid,
    interface_uid,
    method_uid,
)
from .md_links import ExtractionResult


def _collect_php_callables(
    root: Any, content_bytes: bytes, path: str
) -> tuple[dict[str, str], dict[tuple[str, str], str], dict[str, str]]:
    """Pre-pass: top-level funcs, (class, method) map, and class-name → uid."""
    funcs: dict[str, str] = {}
    methods: dict[tuple[str, str], str] = {}
    classes: dict[str, str] = {}

    def walk(node: Any, cur_class: str | None) -> None:
        t = node.type
        if t in ("class_declaration", "interface_declaration", "trait_declaration"):
            nm = _find_field(node, "name")
            cname = _node_text(nm, content_bytes) if nm is not None else ""
            if cname:
                classes[cname] = (
                    interface_uid(path, cname)
                    if t == "interface_declaration"
                    else class_uid(path, cname)
                )
            for c in node.children:
                walk(c, cname or cur_class)
            return
        if t == "function_definition":
            nm = _find_field(node, "name")
            name = _node_text(nm, content_bytes) if nm is not None else ""
            if name and cur_class is None:
                funcs[name] = func_uid(path, name)
        elif t == "method_declaration" and cur_class:
            nm = _find_field(node, "name")
            name = _node_text(nm, content_bytes) if nm is not None else ""
            if name:
                methods[(cur_class, name)] = method_uid(path, cur_class, name)
        for c in node.children:
            walk(c, cur_class)

    walk(root, None)
    return funcs, methods, classes


def _enclosing_php_scope(
    node: Any, content_bytes: bytes, path: str
) -> tuple[str | None, str | None]:
    """Return (enclosing_uid, enclosing_class_name) for a call node."""
    cur = node.parent
    while cur is not None:
        if cur.type == "method_declaration":
            nm = _find_field(cur, "name")
            mname = _node_text(nm, content_bytes) if nm is not None else ""
            cls = cur.parent
            while cls is not None and cls.type not in (
                "class_declaration",
                "interface_declaration",
                "trait_declaration",
            ):
                cls = cls.parent
            cname = ""
            if cls is not None:
                cn = _find_field(cls, "name")
                cname = _node_text(cn, content_bytes) if cn is not None else ""
            if mname and cname:
                return method_uid(path, cname, mname), cname
        if cur.type == "function_definition":
            nm = _find_field(cur, "name")
            name = _node_text(nm, content_bytes) if nm is not None else ""
            return (func_uid(path, name) if name else None), None
        cur = cur.parent
    return None, None


def _walk_php_calls(
    root: Any,
    content_bytes: bytes,
    *,
    path: str,
    normalised: str,
    module_uid_str: str,
    imported: dict[str, str],
    result: ExtractionResult,
) -> None:
    funcs, methods, classes = _collect_php_callables(root, content_bytes, path)
    if not funcs and not methods and not classes:
        return
    seen: set[tuple[str, str, str]] = set()
    stack = [root]
    while stack:
        node = stack.pop()
        t = node.type
        if t in (
            "function_call_expression",
            "member_call_expression",
            "scoped_call_expression",
            "object_creation_expression",
        ):
            src_uid, enc_class = _enclosing_php_scope(node, content_bytes, path)
            src = src_uid or module_uid_str
            target: str | None = None
            edge_type = "calls"
            conf = 0.9
            signal = "php_same_scope"
            line = node.start_point[0] + 1
            if t == "function_call_expression":
                fn = _find_field(node, "function")
                if fn is not None and fn.type == "name":
                    target = funcs.get(_node_text(fn, content_bytes))
            elif t == "member_call_expression":
                obj = _find_field(node, "object")
                nm = _find_field(node, "name")
                method = _node_text(nm, content_bytes) if nm is not None else ""
                if obj is not None and obj.type == "variable_name" and method:
                    var = _node_text(obj, content_bytes).lstrip("$")
                    if var == "this" and enc_class:
                        target = methods.get((enc_class, method))
            elif t == "scoped_call_expression":
                scope = _find_field(node, "scope")
                nm = _find_field(node, "name")
                method = _node_text(nm, content_bytes) if nm is not None else ""
                if scope is not None and method:
                    stext = _node_text(scope, content_bytes).strip()
                    if stext in ("self", "static", "parent") and enc_class:
                        target = methods.get((enc_class, method))
                    else:
                        target = methods.get((_php_short(stext), method))
            elif t == "object_creation_expression":
                cls_node = next(
                    (c for c in node.children if c.type in ("name", "qualified_name")), None
                )
                if cls_node is not None:
                    cname = _php_short(_node_text(cls_node, content_bytes))
                    edge_type = "constructs"
                    target = classes.get(cname)
                    if target is None:
                        # imported / external class — still a real instantiation.
                        target = _resolve_php_type(cname, {}, imported)
                        conf = 0.3 if ":unresolved:" in target else 0.6
                        signal = "php_construct"
            if target and target != src:
                key = (src, target, edge_type)
                if key not in seen:
                    seen.add(key)
                    result.edges.append(
                        GraphEdge(
                            source_uid=src,
                            target_uid=target,
                            edge_type=edge_type,
                            extractor=EXTRACTOR_ID,
                            confidence=conf,
                            source_span=f"{normalised}:{line}",
                            evidence=(EvidenceSignal(signal, conf),),
                        )
                    )
        stack.extend(node.children)
