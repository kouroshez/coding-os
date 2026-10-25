"""Which class a function's local names are bound to, for `x.method()` resolution.

Leaf module: reads one function's AST; the visitor stores the result per uid.
"""

from __future__ import annotations

import ast
import re

from ._python_decls import _dotted_name

_DOTTED_IDENTIFIER = re.compile(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*")


def _annotation_type(annotation: ast.AST | None) -> str | None:
    """The single class an annotation names: `X`, `pkg.X`, `"X"`, `X | None`, `Optional[X]`."""
    if annotation is None:
        return None
    if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
        text = annotation.value.strip()
        return text if _DOTTED_IDENTIFIER.fullmatch(text) else None
    if isinstance(annotation, (ast.Name, ast.Attribute)):
        return _dotted_name(annotation) or None
    if isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
        sides = [
            side
            for side in (annotation.left, annotation.right)
            if not (isinstance(side, ast.Constant) and side.value is None)
        ]
        return _annotation_type(sides[0]) if len(sides) == 1 else None
    if isinstance(annotation, ast.Subscript) and _dotted_name(annotation.value).endswith(
        "Optional"
    ):
        return _annotation_type(annotation.slice)
    return None


def _local_receiver_types(function: ast.AST) -> dict[str, str]:
    """Names a function binds to one known class; a name seen with two types is dropped."""
    found: dict[str, str | None] = {}

    def note(name: str, type_name: str | None) -> None:
        if not type_name:
            return
        found[name] = None if name in found and found[name] != type_name else type_name

    arguments = function.args  # type: ignore[attr-defined]
    for argument in [*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs]:
        if argument.arg not in ("self", "cls"):
            note(argument.arg, _annotation_type(argument.annotation))
    stack: list[ast.AST] = list(function.body)  # type: ignore[attr-defined]
    while stack:
        statement = stack.pop()
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
            note(statement.target.id, _annotation_type(statement.annotation))
        elif (
            isinstance(statement, ast.Assign)
            and len(statement.targets) == 1
            and isinstance(statement.targets[0], ast.Name)
            and isinstance(statement.value, ast.Call)
        ):
            callee = _dotted_name(statement.value.func)
            if callee and callee.split(".")[-1][:1].isupper():
                note(statement.targets[0].id, callee)
        stack.extend(ast.iter_child_nodes(statement))
    return {name: type_name for name, type_name in found.items() if type_name}
