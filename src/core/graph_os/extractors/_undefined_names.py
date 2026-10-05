"""graph_os — names a file uses but never binds: the trace of a forgotten import.

Python goes through the stdlib `symtable`, the compiler's own scope analysis: a
name read at module scope, or a free name inside a function or class, that the
module never assigns, imports or defines and that is no builtin. A file with a
star import is skipped, since any name could come through it.

TS / JS checks the places a missing import breaks at runtime — a call, a `new`
and a JSX component — against every name the file declares anywhere (imports,
declarations, parameters, destructuring) and the language and platform globals.
Declared-anywhere is deliberately loose: it can miss a name used outside its
scope, never invent one.
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
    }
)

_SCRIPT_GLOBALS = frozenset(
    [
        "parseInt",
        "parseFloat",
        "isNaN",
        "isFinite",
        "encodeURIComponent",
        "decodeURIComponent",
        "encodeURI",
        "decodeURI",
        "escape",
        "unescape",
        "eval",
        "require",
        "structuredClone",
        "queueMicrotask",
        "reportError",
        "globalThis",
        "setTimeout",
        "clearTimeout",
        "setInterval",
        "clearInterval",
        "setImmediate",
        "clearImmediate",
        "requestAnimationFrame",
        "cancelAnimationFrame",
        "requestIdleCallback",
        "cancelIdleCallback",
        "fetch",
        "alert",
        "confirm",
        "prompt",
        "atob",
        "btoa",
        "addEventListener",
        "removeEventListener",
        "dispatchEvent",
        "postMessage",
        "importScripts",
        "close",
        "open",
        "print",
        "getComputedStyle",
        "matchMedia",
        "getSelection",
        "scroll",
        "scrollTo",
        "scrollBy",
        "createImageBitmap",
        "describe",
        "it",
        "test",
        "expect",
        "beforeEach",
        "afterEach",
        "beforeAll",
        "afterAll",
        "before",
        "after",
        "context",
        "specify",
        "suite",
        "jest",
        "vi",
        "xit",
        "xdescribe",
        "xtest",
        "fit",
        "fdescribe",
        "Symbol",
        "BigInt",
        "Number",
        "String",
        "Boolean",
        "Array",
        "Object",
        "Date",
        "Function",
        "Error",
        "TypeError",
        "RangeError",
        "SyntaxError",
        "ReferenceError",
        "EvalError",
        "URIError",
        "AggregateError",
        "DOMException",
        "Promise",
        "Map",
        "Set",
        "WeakMap",
        "WeakSet",
        "WeakRef",
        "FinalizationRegistry",
        "Proxy",
        "Reflect",
        "RegExp",
        "JSON",
        "Math",
        "Intl",
        "ArrayBuffer",
        "SharedArrayBuffer",
        "DataView",
        "Int8Array",
        "Uint8Array",
        "Uint8ClampedArray",
        "Int16Array",
        "Uint16Array",
        "Int32Array",
        "Uint32Array",
        "Float32Array",
        "Float64Array",
        "BigInt64Array",
        "BigUint64Array",
        "URL",
        "URLSearchParams",
        "FormData",
        "Headers",
        "Request",
        "Response",
        "Blob",
        "File",
        "FileReader",
        "AbortController",
        "AbortSignal",
        "TextEncoder",
        "TextDecoder",
        "ReadableStream",
        "WritableStream",
        "TransformStream",
        "WebSocket",
        "Worker",
        "SharedWorker",
        "MessageChannel",
        "BroadcastChannel",
        "XMLHttpRequest",
        "EventSource",
        "DOMParser",
        "XMLSerializer",
        "Event",
        "CustomEvent",
        "EventTarget",
        "MouseEvent",
        "KeyboardEvent",
        "PointerEvent",
        "TouchEvent",
        "FocusEvent",
        "InputEvent",
        "ErrorEvent",
        "MessageEvent",
        "ProgressEvent",
        "ClipboardEvent",
        "DragEvent",
        "WheelEvent",
        "AnimationEvent",
        "TransitionEvent",
        "StorageEvent",
        "PopStateEvent",
        "HashChangeEvent",
        "DataTransfer",
        "ClipboardItem",
        "DOMPoint",
        "DOMRect",
        "DOMMatrix",
        "Range",
        "Option",
        "Image",
        "Audio",
        "Path2D",
        "OffscreenCanvas",
        "ImageData",
        "ImageBitmap",
        "MediaRecorder",
        "MediaStream",
        "AudioContext",
        "Notification",
        "IntersectionObserver",
        "ResizeObserver",
        "MutationObserver",
        "PerformanceObserver",
        "FontFace",
        "CSSStyleSheet",
        "Element",
        "HTMLElement",
        "Node",
        "Document",
        "DocumentFragment",
        "Text",
        "Comment",
        "HTMLRewriter",
    ]
)
_DECLARING_FIELDS = {
    "function_declaration": "name",
    "generator_function_declaration": "name",
    "function_expression": "name",
    "class_declaration": "name",
    "abstract_class_declaration": "name",
    "class": "name",
    "interface_declaration": "name",
    "type_alias_declaration": "name",
    "enum_declaration": "name",
    "internal_module": "name",
    "module": "name",
}
_PATTERN_LEAVES = frozenset({"identifier", "shorthand_property_identifier_pattern"})
_PATTERNS = frozenset(
    {
        "object_pattern",
        "array_pattern",
        "rest_pattern",
        "pair_pattern",
        "assignment_pattern",
        "object_assignment_pattern",
        *_PATTERN_LEAVES,
    }
)
_JSX_TAGS = frozenset({"jsx_opening_element", "jsx_self_closing_element"})


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
    defined |= _declared_global_and_assigned(top)
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
    return _with_lines(unbound | (_annotation_names(tree) - _bound_anywhere(tree)), tree)


def _annotation_names(tree: ast.Module) -> set[str]:
    # `from __future__ import annotations` keeps annotations out of symtable,
    # yet a name only an annotation uses is still an import the checker needs.
    annotations: list[ast.expr] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            arguments = node.args
            every = [*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs]
            every += [arg for arg in (arguments.vararg, arguments.kwarg) if arg is not None]
            annotations += [arg.annotation for arg in every if arg.annotation is not None]
            if node.returns is not None:
                annotations.append(node.returns)
        elif isinstance(node, ast.AnnAssign):
            annotations.append(node.annotation)
    return {
        name.id
        for annotation in annotations
        for name in ast.walk(annotation)
        if isinstance(name, ast.Name) and name.id not in _PYTHON_KNOWN
    }


def _bound_anywhere(tree: ast.Module) -> set[str]:
    bound: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            bound.add(node.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(node.name)
            bound.update(param.name for param in getattr(node, "type_params", []))
        elif isinstance(node, ast.arg):
            bound.add(node.arg)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            bound.update((alias.asname or alias.name).split(".")[0] for alias in node.names)
        elif isinstance(node, ast.TypeAlias):
            bound.add(node.name.id)
    return bound


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


def _with_lines(names: set[str], tree: ast.Module) -> list[list[Any]]:
    first: dict[str, int] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in names:
            first[node.id] = min(first.get(node.id, node.lineno), node.lineno)
    return sorted(([name, first.get(name)] for name in names), key=lambda item: item[1] or 0)


def script_undefined(root: Any) -> list[list[Any]]:
    declared = _script_declared(root)
    found: dict[str, int] = {}
    for name, line in _script_uses(root):
        if name not in declared and name not in _SCRIPT_GLOBALS and name not in found:
            found[name] = line
    return sorted(([name, line] for name, line in found.items()), key=lambda item: item[1])


def _script_declared(root: Any) -> set[str]:
    names: set[str] = set()
    stack = [root]
    while stack:
        node = stack.pop()
        kind = node.type
        if kind in _DECLARING_FIELDS:
            _add_text(node.child_by_field_name(_DECLARING_FIELDS[kind]), names)
        elif kind == "variable_declarator":
            _pattern_names(node.child_by_field_name("name"), names)
        elif kind in ("required_parameter", "optional_parameter"):
            _pattern_names(node.child_by_field_name("pattern"), names)
        elif kind == "arrow_function":
            _add_text(node.child_by_field_name("parameter"), names)
        elif kind == "formal_parameters":
            for child in node.named_children:
                if child.type in _PATTERNS:
                    _pattern_names(child, names)
        elif kind == "catch_clause":
            _pattern_names(node.child_by_field_name("parameter"), names)
        elif kind == "for_in_statement":
            _pattern_names(node.child_by_field_name("left"), names)
        elif kind == "import_specifier":
            _add_text(node.child_by_field_name("alias") or node.child_by_field_name("name"), names)
        elif kind in ("import_clause", "namespace_import", "import_require_clause"):
            for child in node.named_children:
                if child.type == "identifier":
                    _add_text(child, names)
        stack.extend(node.children)
    return names


def _pattern_names(node: Any, names: set[str]) -> None:
    if node is None:
        return
    if node.type in _PATTERN_LEAVES:
        _add_text(node, names)
    elif node.type == "pair_pattern":
        _pattern_names(node.child_by_field_name("value"), names)
    elif node.type in ("assignment_pattern", "object_assignment_pattern"):
        _pattern_names(node.child_by_field_name("left"), names)
    else:
        for child in node.named_children:
            if child.type in _PATTERNS:
                _pattern_names(child, names)


def _add_text(node: Any, names: set[str]) -> None:
    if node is not None and node.text:
        names.add(node.text.decode("utf-8", "replace"))


def _script_uses(root: Any) -> list[tuple[str, int]]:
    uses: list[tuple[str, int]] = []
    stack = [root]
    while stack:
        node = stack.pop()
        line = node.start_point[0] + 1
        if node.type in _JSX_TAGS:
            name = _jsx_root(node.child_by_field_name("name"))
            if name:
                uses.append((name, line))
        elif node.type in ("call_expression", "new_expression"):
            field = "function" if node.type == "call_expression" else "constructor"
            callee = node.child_by_field_name(field)
            if callee is not None and callee.type == "identifier" and callee.text:
                uses.append((callee.text.decode("utf-8", "replace"), line))
        stack.extend(node.children)
    return uses


def _jsx_root(name: Any) -> str | None:
    # `<div>` is an intrinsic element; `<Card>` and `<Form.Field>` need a binding.
    if name is None or not name.text:
        return None
    if name.type == "identifier":
        text = name.text.decode("utf-8", "replace")
        return text if text[:1].isupper() else None
    while name.type in ("member_expression", "nested_identifier") and name.named_children:
        name = name.named_children[0]
    return name.text.decode("utf-8", "replace") if name.type == "identifier" else None
