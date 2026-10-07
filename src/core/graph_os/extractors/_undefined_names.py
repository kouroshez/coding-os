"""graph_os — names a file uses but never binds: the trace of a forgotten import.

TS / JS checks the places a missing import breaks at runtime — a call, a `new`
and a JSX component — against every name the file declares anywhere (imports,
declarations, parameters, destructuring) and the language and platform globals.
Declared-anywhere is deliberately loose: it can miss a name used outside its
scope, never invent one. Python's report is _undefined_python.
"""

from __future__ import annotations

from typing import Any

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
