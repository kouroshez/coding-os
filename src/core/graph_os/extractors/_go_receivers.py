"""graph_os — the static type of a Go method call's receiver.

A parse knows a value's type wherever the source spells it: a parameter, `var x T`,
`x := T{}` / `&T{}` / `new(T)`, a struct field, a function's result. A type
declared in this file answers at once; a field of a struct or the result of a
function declared in another file of the package becomes a stub the Go linker
resolves from that declaration's `go_fields` / `go_result` metadata. Imports the
`_go_uids` leaf only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ._go_uids import (
    _GO_BUILTIN_TYPES,
    GO_BUILTIN_FUNCTIONS,
    _find_child,
    _find_field,
    _node_text,
    package_symbol_stub,
)

GoImportsByName = dict[str, tuple[str, str | None]]


@dataclass(frozen=True)
class GoType:
    # The type's own stub: `code:external:gopkg:<dir>:T`, `code:external:<import>:T`,
    # or the deferred `code:external:gopkg:<dir>:F()` for a result not known yet.
    key: str

    def member(self, *names: str) -> str:
        return ".".join((self.key, *names))


@dataclass(frozen=True)
class GoFileTypes:
    struct_fields: dict[str, dict[str, GoType]]
    results: dict[str, GoType]


def go_type(
    node: Any, content_bytes: bytes, directory: str, imports: GoImportsByName
) -> GoType | None:
    while node is not None and node.type in ("pointer_type", "parenthesized_type"):
        node = node.named_children[0] if node.named_children else None
    if node is not None and node.type == "generic_type":
        node = _find_field(node, "type")
    if node is None:
        return None
    if node.type == "type_identifier":
        name = _node_text(node, content_bytes)
        return None if name in _GO_BUILTIN_TYPES else GoType(package_symbol_stub(directory, name))
    if node.type != "qualified_type":
        return None
    package, name_node = _find_field(node, "package"), _find_field(node, "name")
    imported = imports.get(_node_text(package, content_bytes)) if package is not None else None
    if imported is None or name_node is None:
        return None
    import_path, package_dir = imported
    name = _node_text(name_node, content_bytes)
    if package_dir:
        return GoType(package_symbol_stub(package_dir, name))
    return GoType(f"code:external:{import_path}:{name}")


def file_types(
    root: Any, content_bytes: bytes, directory: str, imports: GoImportsByName
) -> GoFileTypes:
    """The struct field types and function result types this file declares."""
    fields: dict[str, dict[str, GoType]] = {}
    results: dict[str, GoType] = {}
    for declaration in root.children:
        if declaration.type == "function_declaration":
            name = _find_field(declaration, "name")
            result = _result_type(declaration, content_bytes, directory, imports)
            if name is not None and result is not None:
                results[_node_text(name, content_bytes)] = result
        elif declaration.type == "type_declaration":
            for spec in declaration.children:
                name, struct = _find_field(spec, "name"), _find_field(spec, "type")
                if (
                    spec.type == "type_spec"
                    and name is not None
                    and struct is not None
                    and struct.type == "struct_type"
                ):
                    fields[_node_text(name, content_bytes)] = _struct_fields(
                        struct, content_bytes, directory, imports
                    )
    return GoFileTypes(fields, results)


def _result_type(
    declaration: Any, content_bytes: bytes, directory: str, imports: GoImportsByName
) -> GoType | None:
    result = _find_field(declaration, "result")
    if result is None:
        return None
    if result.type != "parameter_list":
        return go_type(result, content_bytes, directory, imports)
    # `(*Service, error)`: the first result with a named type is the value.
    for parameter in result.named_children:
        typ = go_type(_find_field(parameter, "type"), content_bytes, directory, imports)
        if typ is not None:
            return typ
    return None


def _struct_fields(
    struct: Any, content_bytes: bytes, directory: str, imports: GoImportsByName
) -> dict[str, GoType]:
    fields: dict[str, GoType] = {}
    field_list = _find_child(struct, "field_declaration_list")
    for declaration in field_list.children if field_list is not None else ():
        type_node = _find_field(declaration, "type")
        typ = go_type(type_node, content_bytes, directory, imports)
        if declaration.type != "field_declaration" or typ is None:
            continue
        names = declaration.children_by_field_name("name")
        # An embedded field is named by its type: `s.Repo.Find()`.
        for name in [_node_text(n, content_bytes) for n in names] or [typ.key.rpartition(":")[2]]:
            fields[name] = typ
    return fields


@dataclass(frozen=True)
class GoValues:
    typed: dict[str, GoType]
    known: GoFileTypes
    directory: str
    imports: GoImportsByName


def scope_types_cached(
    declaration: Any,
    content_bytes: bytes,
    directory: str,
    imports: GoImportsByName,
    known: GoFileTypes,
    cache: dict[tuple[int, int], dict[str, GoType]],
) -> dict[str, GoType]:
    if declaration is None:
        return {}
    key = (declaration.start_byte, declaration.end_byte)
    if key not in cache:
        cache[key] = scope_types(declaration, content_bytes, directory, imports, known)
    return cache[key]


def operand_type(
    operand: Any, receiver_var: str, receiver_type: str, content_bytes: bytes, values: GoValues
) -> GoType | None:
    """The type of `F()`, `recv.field` or `local.field` in front of a method call."""
    if operand.type == "call_expression":
        return value_type(operand, content_bytes, values.directory, values.imports, values.known)
    if operand.type != "selector_expression":
        return None
    inner, field = _find_field(operand, "operand"), _find_field(operand, "field")
    if inner is None or field is None or inner.type != "identifier":
        return None
    name, field_name = _node_text(inner, content_bytes), _node_text(field, content_bytes)
    if receiver_var and name == receiver_var:
        owner, type_name = package_symbol_stub(values.directory, receiver_type), receiver_type
    elif name in values.typed:
        owner, type_name = values.typed[name].key, values.typed[name].key.rpartition(":")[2]
    else:
        return None
    if owner == package_symbol_stub(values.directory, type_name):
        declared = values.known.struct_fields.get(type_name, {}).get(field_name)
        if declared is not None:
            return declared
    # A struct declared in another file: the linker reads its `go_fields`.
    if owner.startswith("code:external:gopkg:") and "(" not in owner:
        return GoType(f"{owner}.{field_name}")
    return None


def scope_types(
    declaration: Any,
    content_bytes: bytes,
    directory: str,
    imports: GoImportsByName,
    known: GoFileTypes,
) -> dict[str, GoType]:
    """Names this function binds to one spelled type; a name bound any other way is left out."""
    bindings: dict[str, set[GoType | None]] = {}
    for name, typ in _bindings(declaration, content_bytes, directory, imports, known):
        bindings.setdefault(name, set()).add(typ)
    typed: dict[str, GoType] = {}
    for name, types in bindings.items():
        only = next(iter(types)) if len(types) == 1 else None
        if only is not None:
            typed[name] = only
    return typed


def _bindings(
    declaration: Any,
    content_bytes: bytes,
    directory: str,
    imports: GoImportsByName,
    known: GoFileTypes,
) -> list[tuple[str, GoType | None]]:
    found: list[tuple[str, GoType | None]] = []
    stack = [declaration]
    while stack:
        node = stack.pop()
        stack.extend(node.children)
        if node.type in ("parameter_declaration", "variadic_parameter_declaration", "var_spec"):
            typ = go_type(_find_field(node, "type"), content_bytes, directory, imports)
            if node.type == "variadic_parameter_declaration":
                typ = None
            found += [
                (_node_text(n, content_bytes), typ) for n in node.children_by_field_name("name")
            ]
        elif node.type in ("short_var_declaration", "assignment_statement", "range_clause"):
            left, right = _find_field(node, "left"), _find_field(node, "right")
            names = list(left.named_children) if left is not None else []
            values = (
                right.named_children
                if right is not None and right.type == "expression_list"
                else []
            )
            for index, name in enumerate(names):
                if name.type != "identifier":
                    continue
                value = values[index] if index < len(values) else None
                if index and len(values) == 1:
                    value = None
                typ = value_type(value, content_bytes, directory, imports, known)
                found.append((_node_text(name, content_bytes), typ))
    return found


def value_type(
    value: Any, content_bytes: bytes, directory: str, imports: GoImportsByName, known: GoFileTypes
) -> GoType | None:
    """The type an expression evaluates to, when its spelling says so."""
    if value is None:
        return None
    if value.type == "unary_expression" and value.named_children:
        value = value.named_children[-1]
    if value.type == "composite_literal":
        return go_type(_find_field(value, "type"), content_bytes, directory, imports)
    if value.type != "call_expression":
        return None
    function = _find_field(value, "function")
    if function is None:
        return None
    if function.type == "identifier":
        name = _node_text(function, content_bytes)
        if name == "new":
            arguments = _find_field(value, "arguments")
            first = (
                arguments.named_children[0]
                if arguments is not None and arguments.named_children
                else None
            )
            return go_type(first, content_bytes, directory, imports)
        if name in known.results:
            return known.results[name]
        if name in GO_BUILTIN_FUNCTIONS or name in _GO_BUILTIN_TYPES:
            return None
        return GoType(package_symbol_stub(directory, f"{name}()"))
    if function.type == "selector_expression":
        package, field = _find_field(function, "operand"), _find_field(function, "field")
        if package is None or field is None or package.type != "identifier":
            return None
        imported = imports.get(_node_text(package, content_bytes))
        if imported is None or not imported[1]:
            return None
        return GoType(
            package_symbol_stub(str(imported[1]), f"{_node_text(field, content_bytes)}()")
        )
    return None
