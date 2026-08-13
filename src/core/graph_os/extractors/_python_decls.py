"""graph_os — Python declaration records and ast-to-text primitives.

Leaf module: the dataclasses the walkers fill in, plus the pure `ast` helpers
that render signatures and expand annotations. Imports no sibling.
"""

from __future__ import annotations

import ast
import hashlib
from dataclasses import dataclass


@dataclass
class _SymbolDecl:
    """One declaration discovered during the AST walk."""

    uid: str
    kind: str
    name: str
    qualname: str
    line: int
    end_line: int | None
    signature: str
    docstring: str | None
    decorators: tuple[str, ...]
    parent_uid: str | None
    is_method: bool = False


@dataclass
class _CallSite:
    caller_uid: str
    callee_name: str  # last segment of the dotted expression
    full_expr: str  # dotted form for later chain resolution
    line: int
    is_constructor_like: bool  # `Foo()` where Foo looks capitalised
    is_await: bool = False  # E5: `await X()` — emits `awaits` edge
    dispatched_uids: tuple[str, ...] = ()  # E6: known-function uids passed as args
    enclosing_class_uid: str | None = None  # GE: class scope for self./cls. method resolution


@dataclass
class _ImportDecl:
    """A single `import X` / `from X import Y` statement."""

    source_module: str | None  # `X` in `from X import Y`
    imported: str  # `Y` (or `X` for plain `import X`)
    local_name: str  # alias if present, else imported
    line: int
    is_wildcard: bool = False


_BUILTIN_TYPES: frozenset[str] = frozenset(
    {
        "str",
        "int",
        "float",
        "bool",
        "bytes",
        "list",
        "dict",
        "tuple",
        "set",
        "frozenset",
        "None",
        "Any",
        "object",
        "type",
        "complex",
        "range",
        "memoryview",
        "bytearray",
        "Path",
        "datetime",
        "date",
        "time",
        "timedelta",
        "Decimal",
    }
)


def _module_docstring(content: str) -> str | None:
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return None
    return ast.get_docstring(tree)


def _hash_decl(decl: _SymbolDecl) -> str:
    key = f"{decl.kind}|{decl.uid}|{decl.signature}|{decl.decorators}"
    return hashlib.sha1(key.encode("utf-8"), usedforsecurity=False).hexdigest()[:12]


def _class_signature(node: ast.ClassDef) -> str:
    bases = ", ".join(_dotted_name(b) for b in node.bases)
    return f"class {node.name}({bases})" if bases else f"class {node.name}"


def _function_param_annotations(node: ast.AST) -> list[str]:
    """Return the annotation names for every annotated parameter of
    ``node`` (a FunctionDef / AsyncFunctionDef).

    Skips `self` and `cls` because their annotation is uninteresting
    (it would always be the surrounding class), and skips parameters
    with no annotation.  Union-style annotations expand to one entry
    per branch so each receiver type emits its own edge.
    """
    args = getattr(node, "args", None)
    if args is None:
        return []
    out: list[str] = []
    pos_args = list(getattr(args, "posonlyargs", []) or []) + list(getattr(args, "args", []) or [])
    for idx, arg in enumerate(pos_args):
        if idx == 0 and arg.arg in ("self", "cls"):
            continue
        if arg.annotation is None:
            continue
        out.extend(_expand_annotation(arg.annotation))
    for arg in getattr(args, "kwonlyargs", []) or []:
        if arg.annotation is None:
            continue
        out.extend(_expand_annotation(arg.annotation))
    if getattr(args, "vararg", None) is not None and args.vararg.annotation is not None:
        out.extend(_expand_annotation(args.vararg.annotation))
    if getattr(args, "kwarg", None) is not None and args.kwarg.annotation is not None:
        out.extend(_expand_annotation(args.kwarg.annotation))
    return out


def _function_return_annotation(node: ast.AST) -> str | None:
    ret = getattr(node, "returns", None)
    if ret is None:
        return None
    flat = _expand_annotation(ret)
    return flat[0] if flat else None


def _expand_annotation(node: ast.AST) -> list[str]:
    """Return one or more dotted names for an annotation node.

    `Foo`                  → ["Foo"]
    `pkg.Foo`              → ["pkg.Foo"]
    `Optional[Foo]`        → ["Foo"]            (None branch dropped)
    `Union[Foo, Bar]`      → ["Foo", "Bar"]
    `Foo | Bar`            → ["Foo", "Bar"]
    `list[Foo]`            → ["Foo"]            (container stripped)
    `Literal["x"]`         → []                 (value-only types skipped)

    Anything we can't recognise yields an empty list — caller will then
    skip the edge entirely rather than emit a stub with bad confidence.
    """
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, ast.Attribute):
        dotted = _dotted_name(node)
        return [dotted] if dotted else []
    if isinstance(node, ast.Constant):
        # `None` annotation → drop (often appears via Optional[...]).
        if node.value is None:
            return []
        # Forward reference as string literal: `"Foo"`.
        if isinstance(node.value, str):
            return [node.value]
        return []
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        # PEP 604 unions: `Foo | Bar | None`.
        return _expand_annotation(node.left) + _expand_annotation(node.right)
    if isinstance(node, ast.Subscript):
        # Container subscripts: `list[Foo]`, `Optional[Foo]`, `Union[Foo, Bar]`,
        # `dict[str, Foo]`.  Walk inside and recurse.
        value_name = (
            _dotted_name(node.value) if isinstance(node.value, (ast.Name, ast.Attribute)) else ""
        )
        slice_node = getattr(node, "slice", None)
        if slice_node is None:
            return []
        # Generic strip — unwrap the container, recurse on the slice.
        if isinstance(slice_node, ast.Tuple):
            return [t for elt in slice_node.elts for t in _expand_annotation(elt)]
        # Special case for `Literal[...]` — types-by-value, not by-class.
        if value_name == "Literal":
            return []
        return _expand_annotation(slice_node)
    if isinstance(node, ast.Tuple):
        return [t for elt in node.elts for t in _expand_annotation(elt)]
    return []


def _function_signature(node: ast.AST, *, is_async: bool) -> str:
    try:
        args = ast.unparse(node.args)  # type: ignore[attr-defined]
    except (AttributeError, TypeError):
        args = ""
    prefix = "async def" if is_async else "def"
    return f"{prefix} {node.name}({args})"  # type: ignore[attr-defined]


def _dotted_name(node: ast.AST) -> str:
    """Best-effort string form of an expression node (Name / Attribute / Call)."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_dotted_name(node.value)}.{node.attr}"
    if isinstance(node, ast.Call):
        return _dotted_name(node.func)
    if isinstance(node, ast.Subscript):
        return _dotted_name(node.value)
    try:
        return ast.unparse(node)
    except Exception:
        return "<expr>"
