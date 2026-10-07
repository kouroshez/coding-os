"""graph_os — where each local name of a Go function is in scope.

Go scopes a parameter, result or type parameter over its whole function, and a
`:=`, `var` or `const` from the end of its own statement to the end of the block
— or of the `if` / `for` / `switch` whose header declares it. So `client :=
client()` still calls the file's `client`, and a later `for _, client := range`
shadows it only inside that loop. A call resolves against the names in scope at
its own position (`bound_at`).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from ._go_uids import _find_field, _node_text

Scopes = dict[str, list[tuple[int, int]]]

_NAME_FIELD_BINDERS = frozenset({"var_spec", "const_spec"})
# Each binds its left side only when written with `:=` (`for k = range m` assigns).
_LEFT_SIDE_BINDERS = frozenset({"short_var_declaration", "range_clause", "receive_statement"})
_PARAMETERS = frozenset({"parameter_declaration", "variadic_parameter_declaration"})
_FUNCTIONS = frozenset({"function_declaration", "method_declaration", "func_literal"})
# A parameter of a function type or an interface method names nothing in a body.
_SIGNATURES = frozenset({"function_type", "method_elem", "method_spec"})
_SCOPE_OWNERS = frozenset(
    {
        "block",
        "if_statement",
        "for_statement",
        "expression_switch_statement",
        "type_switch_statement",
        "select_statement",
        "expression_case",
        "type_case",
        "communication_case",
        "default_case",
    }
)


def binding_scopes(declaration: Any, content_bytes: bytes) -> Scopes:
    """Each locally bound name and the byte ranges it is in scope over."""
    scopes: Scopes = defaultdict(list)
    whole = (declaration.start_byte, declaration.end_byte)
    stack = [declaration]
    while stack:
        node = stack.pop()
        if node.type in _PARAMETERS:
            owner = _function_of(node)
            if owner is not None:
                for name in node.children_by_field_name("name"):
                    scopes[_node_text(name, content_bytes)].append(
                        (owner.start_byte, owner.end_byte)
                    )
        elif node.type == "type_parameter_declaration":
            for name in node.children_by_field_name("name"):
                scopes[_node_text(name, content_bytes)].append(whole)
        elif node.type in _NAME_FIELD_BINDERS:
            span = (node.end_byte, _scope_end(node, whole[1]))
            for name in node.children_by_field_name("name"):
                scopes[_node_text(name, content_bytes)].append(span)
        elif node.type in _LEFT_SIDE_BINDERS and any(c.type == ":=" for c in node.children):
            span = (node.end_byte, _scope_end(node, whole[1]))
            for name in _identifier_texts(_find_field(node, "left"), content_bytes):
                scopes[name].append(span)
        elif node.type == "type_switch_statement":
            # `switch cause := err.(type)` binds `cause` in the cases, not in its own header.
            alias = _find_field(node, "alias")
            if alias is not None:
                header = _find_field(node, "value") or alias
                for name in _identifier_texts(alias, content_bytes):
                    scopes[name].append((header.end_byte, node.end_byte))
        stack.extend(node.children)
    if declaration.type == "method_declaration":
        for name in receiver_type_arguments(declaration, content_bytes):
            scopes[name].append(whole)
    return dict(scopes)


def bound_at(scopes: Scopes, offset: int) -> set[str]:
    """The local names in scope at byte `offset`."""
    return {
        name for name, spans in scopes.items() if any(start <= offset < end for start, end in spans)
    }


def receiver_type_arguments(method: Any, content_bytes: bytes) -> set[str]:
    # `func (b *Box[Item]) Put()` binds Item for the method body.
    names: set[str] = set()
    receiver = _find_field(method, "receiver")
    stack = [receiver] if receiver is not None else []
    while stack:
        node = stack.pop()
        if node.type == "type_arguments":
            names.update(
                _node_text(leaf, content_bytes)
                for elem in node.named_children
                for leaf in elem.named_children
                if leaf.type == "type_identifier"
            )
        stack.extend(node.children)
    return names


def _function_of(parameter: Any) -> Any | None:
    node = parameter.parent
    while node is not None:
        if node.type in _FUNCTIONS:
            return node
        if node.type in _SIGNATURES:
            return None
        node = node.parent
    return None


def _scope_end(node: Any, fallback: int) -> int:
    parent = node.parent
    while parent is not None:
        if parent.type in _SCOPE_OWNERS:
            return int(parent.end_byte)
        parent = parent.parent
    return fallback


def _identifier_texts(node: Any, content_bytes: bytes) -> list[str]:
    if node is None:
        return []
    if node.type == "identifier":
        return [_node_text(node, content_bytes)]
    return [_node_text(c, content_bytes) for c in node.children if c.type == "identifier"]
