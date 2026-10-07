"""graph_os — Python names a file uses but never binds: the trace of a forgotten import.

The stdlib `symtable`, the compiler's own scope analysis, reports a name read at
module scope, or a free name inside a function or class, that the module never
assigns, imports or defines and that is no builtin. A walrus in a module-level
comprehension binds at module scope, which symtable does not show. Annotations
are checked apart: under `from __future__ import annotations` symtable never
sees them, nor the names inside a string annotation, so each annotation's names —
read out of the string when it is one (capitalised names only: a forward
reference names a class, `"username"` is prose), never out of `Literal[...]` or
`Annotated` metadata — must be bound at module level or in a function or class
that encloses the annotation. A file with a star import is skipped, since any
name could come through it.
"""

from __future__ import annotations

import ast
import builtins
import symtable
from typing import Any

_PYTHON_KNOWN = frozenset(dir(builtins)) | frozenset(
    {
        "__name__",
        "__file__",
        "__doc__",
        "__package__",
        "__spec__",
        "__loader__",
        "__builtins__",
        "__path__",
        "__annotations__",
        "__cached__",
        "__dict__",
        # Bound in every class body.
        "__module__",
        "__qualname__",
    }
)
_COMPREHENSIONS = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)
# `type X = ...` arrived in 3.12; on 3.10/3.11 the class is absent, not just unused.
_TYPE_ALIAS: Any = getattr(ast, "TypeAlias", None)


def python_undefined(content: str, tree: ast.Module) -> list[list[Any]]:
    if any(
        isinstance(node, ast.ImportFrom) and any(alias.name == "*" for alias in node.names)
        for node in ast.walk(tree)
    ):
        return []
    try:
        top = symtable.symtable(content, "<graph>", "exec")
    except (SyntaxError, ValueError):
        return []
    defined = {
        symbol.get_name()
        for symbol in top.get_symbols()
        if symbol.is_assigned()
        or symbol.is_imported()
        or symbol.is_namespace()
        or symbol.is_parameter()
    }
    defined |= _declared_global_and_assigned(top) | _module_walrus_targets(tree)
    unbound: set[str] = set()
    tables = [top]
    while tables:
        table = tables.pop()
        for symbol in table.get_symbols():
            name = symbol.get_name()
            module_level = table.get_type() == "module" or (
                symbol.is_global() and not symbol.is_local()
            )
            if (
                symbol.is_referenced()
                and module_level
                and name not in defined
                and name not in _PYTHON_KNOWN
            ):
                unbound.add(name)
        tables.extend(table.get_children())
    lines = _first_lines(unbound, tree)
    for name, line in _unbound_annotations(tree, frozenset(defined)).items():
        lines.setdefault(name, line)
    return sorted(([name, line] for name, line in lines.items()), key=lambda item: item[1] or 0)


def _module_walrus_targets(tree: ast.Module) -> set[str]:
    # `[last := f(x) for x in xs]` at module level binds `last` in the module.
    targets: set[str] = set()
    stack: list[tuple[ast.AST, bool]] = [(tree, False)]
    while stack:
        node, in_comprehension = stack.pop()
        if isinstance(node, _SCOPES):
            continue
        if (
            in_comprehension
            and isinstance(node, ast.NamedExpr)
            and isinstance(node.target, ast.Name)
        ):
            targets.add(node.target.id)
        inside = in_comprehension or isinstance(node, _COMPREHENSIONS)
        stack.extend((child, inside) for child in ast.iter_child_nodes(node))
    return targets


def _declared_global_and_assigned(top: symtable.SymbolTable) -> set[str]:
    names: set[str] = set()
    tables = list(top.get_children())
    while tables:
        table = tables.pop()
        names.update(
            symbol.get_name()
            for symbol in table.get_symbols()
            if symbol.is_declared_global() and symbol.is_assigned()
        )
        tables.extend(table.get_children())
    return names


def _unbound_annotations(tree: ast.Module, module_bound: frozenset[str]) -> dict[str, int]:
    found: dict[str, int] = {}

    def check(annotation: ast.expr, bound: frozenset[str]) -> None:
        for name, line in _annotation_names(annotation):
            if name not in bound and name not in _PYTHON_KNOWN:
                found.setdefault(name, line)

    stack: list[tuple[ast.AST, frozenset[str]]] = [(tree, module_bound)]
    while stack:
        node, bound = stack.pop()
        for child in ast.iter_child_nodes(node):
            inner = bound
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                inner = bound | {param.name for param in getattr(child, "type_params", [])}
                if not isinstance(child, ast.ClassDef):
                    for annotation in _signature_annotations(child):
                        check(annotation, inner)
                inner = inner | _scope_bound(child)
            elif isinstance(child, ast.AnnAssign):
                check(child.annotation, bound)
            stack.append((child, inner))
    return found


def _signature_annotations(function: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.expr]:
    arguments = function.args
    every = [*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs]
    every += [arg for arg in (arguments.vararg, arguments.kwarg) if arg is not None]
    annotations = [arg.annotation for arg in every if arg.annotation is not None]
    return annotations + ([function.returns] if function.returns is not None else [])


def _annotation_names(node: ast.expr) -> list[tuple[str, int]]:
    if isinstance(node, ast.Constant):
        if not isinstance(node.value, str):
            return []
        try:
            parsed = ast.parse(node.value.strip(), mode="eval").body
        except SyntaxError:
            return []
        names = _annotation_names(parsed)
        if isinstance(parsed, ast.Name):
            # A bare forward reference names a class; `name: "username"` is prose.
            names = [(name, line) for name, line in names if name[:1].isupper()]
        return [(name, node.lineno) for name, _ in names]
    if isinstance(node, ast.Name):
        return [(node.id, node.lineno)]
    if isinstance(node, ast.Attribute):
        return _annotation_names(node.value)
    if isinstance(node, ast.Subscript):
        base = node.value
        head = base.attr if isinstance(base, ast.Attribute) else getattr(base, "id", "")
        arguments = list(node.slice.elts) if isinstance(node.slice, ast.Tuple) else [node.slice]
        # `Literal["red"]` holds values, and only `Annotated[T, meta]`'s first argument is a type.
        arguments = [] if head == "Literal" else arguments[:1] if head == "Annotated" else arguments
        return _annotation_names(base) + [
            name for argument in arguments for name in _annotation_names(argument)
        ]
    return [
        found
        for child in ast.iter_child_nodes(node)
        if isinstance(child, ast.expr)
        for found in _annotation_names(child)
    ]


def _scope_bound(scope: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> frozenset[str]:
    # Names bound directly in a function or class body; nested scopes keep theirs.
    bound: set[str] = set()
    if not isinstance(scope, ast.ClassDef):
        arguments = scope.args
        every = [*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs]
        bound.update(arg.arg for arg in [*every, arguments.vararg, arguments.kwarg] if arg)
    stack: list[ast.AST] = list(scope.body)
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(node.name)
            continue
        if isinstance(node, ast.Lambda):
            continue
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            bound.add(node.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            bound.update((alias.asname or alias.name).split(".")[0] for alias in node.names)
        elif _TYPE_ALIAS is not None and isinstance(node, _TYPE_ALIAS):
            bound.add(node.name.id)
        stack.extend(ast.iter_child_nodes(node))
    return frozenset(bound)


def _first_lines(names: set[str], tree: ast.Module) -> dict[str, int]:
    first: dict[str, int] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in names:
            first[node.id] = min(first.get(node.id, node.lineno), node.lineno)
    return {name: first.get(name, 0) for name in names}
