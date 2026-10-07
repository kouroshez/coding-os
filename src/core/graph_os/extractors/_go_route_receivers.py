"""graph_os — which Go expression in front of a call is a Fiber router.

A route's receiver is not always a name: a struct field holding the app
(`s.app.Get`), an inline group (`app.Group("/admin").Get`), a Fiber v3 route
chain (`app.RouteChain("/events").Get(h).Post(h)`) or a domain
(`app.Domain("api.example.com").Get`). Each gets a key in the function's
routers, built on its parent, so the prefix walk treats it like a named one.
Leaf of the route walker (_go_routes); imports only the route model.
"""

from __future__ import annotations

from typing import Any

from ._go_route_emit import _arguments, _Function, _Router
from ._go_uids import _find_field, _node_text

_ROUTER_TYPES = frozenset({"App", "Router", "Group"})
_STRINGS = frozenset({"interpreted_string_literal", "raw_string_literal"})
_VERBS = frozenset(
    {"Get", "Post", "Put", "Patch", "Delete", "Head", "Options", "Connect", "Trace", "All"}
)


def selector_call(node: Any, function: _Function) -> tuple[str, str, list[Any]]:
    """(router key, member, arguments) of `<receiver>.<member>(...)`."""
    if node is None or node.type != "call_expression":
        return "", "", []
    callee = _find_field(node, "function")
    if callee is None or callee.type != "selector_expression":
        return "", "", []
    operand, member = _find_field(callee, "operand"), _find_field(callee, "field")
    if operand is None or member is None:
        return "", "", []
    receiver = _receiver_key(operand, function)
    if not receiver:
        return "", "", []
    return receiver, _node_text(member, function.content), _arguments(node)


def _receiver_key(operand: Any, function: _Function) -> str:
    if operand.type == "identifier":
        return _node_text(operand, function.content)
    key = _node_text(operand, function.content)
    if operand.type == "selector_expression":
        inner, field = _find_field(operand, "operand"), _find_field(operand, "field")
        if inner is None or field is None or inner.type != "identifier":
            return ""
        if _node_text(inner, function.content) == function.scope.receiver_var:
            owner = (function.scope.receiver_type, _node_text(field, function.content))
            router_type = function.field_routers.get(owner)
            if router_type:
                function.routers.setdefault(key, _Router(known=router_type == "App"))
        return key
    if operand.type != "call_expression":
        return ""
    parent, member, arguments = selector_call(operand, function)
    router = function.routers.get(parent)
    if router is None:
        return ""
    if member in _VERBS and router.chain:
        return parent  # a chain's verb returns the chain
    segment = string_argument(arguments, 0, function)
    if member in ("Group", "RouteChain"):
        function.routers.setdefault(
            key,
            _Router(
                parent=parent,
                segment=segment or "",
                known=segment is not None,
                chain=member == "RouteChain",
            ),
        )
    elif member == "Domain":
        function.routers.setdefault(key, _Router(parent=parent))
    else:
        return ""
    return key


def string_argument(arguments: list[Any], index: int, function: _Function) -> str | None:
    if len(arguments) <= index or arguments[index].type not in _STRINGS:
        return None
    return _node_text(arguments[index], function.content)[1:-1]


def method_list(argument: Any, function: _Function) -> list[str]:
    # `app.Add("GET", …)` or `app.Add([]string{"GET", "POST"}, …)`.
    if argument.type in _STRINGS:
        return [_node_text(argument, function.content)[1:-1].upper()]
    if argument.type != "composite_literal":
        return []
    body = _find_field(argument, "body")
    values = [
        leaf
        for element in (body.named_children if body is not None else [])
        for leaf in ([element] if element.type in _STRINGS else element.named_children)
        if leaf.type in _STRINGS
    ]
    return [_node_text(value, function.content)[1:-1].upper() for value in values]


def router_type(type_node: Any, content: bytes, aliases: set[str]) -> str | None:
    while type_node is not None and type_node.type == "pointer_type":
        type_node = next(iter(type_node.named_children), None)
    if type_node is None or type_node.type != "qualified_type":
        return None
    package, name = _find_field(type_node, "package"), _find_field(type_node, "name")
    if package is None or name is None or _node_text(package, content) not in aliases:
        return None
    type_name = _node_text(name, content)
    return type_name if type_name in _ROUTER_TYPES else None


def struct_router_fields(
    root: Any, content: bytes, aliases: set[str]
) -> dict[tuple[str, str], str]:
    """(struct, field) → router type for fields that hold a Fiber app, router or group."""
    fields: dict[tuple[str, str], str] = {}
    stack = [root]
    while stack:
        node = stack.pop()
        stack.extend(node.children)
        if node.type != "type_spec":
            continue
        name, struct = _find_field(node, "name"), _find_field(node, "type")
        if name is None or struct is None or struct.type != "struct_type":
            continue
        for declaration in _field_declarations(struct):
            kind = router_type(_find_field(declaration, "type"), content, aliases)
            for field in declaration.children_by_field_name("name") if kind else ():
                fields[(_node_text(name, content), _node_text(field, content))] = str(kind)
    return fields


def _field_declarations(struct: Any) -> list[Any]:
    return [
        declaration
        for child in struct.named_children
        if child.type == "field_declaration_list"
        for declaration in child.named_children
        if declaration.type == "field_declaration"
    ]
