"""graph_os — Go call and construction edges.

Two paths that coexist: a regex pass for qualified `pkg.Func(...)` receivers that
survives without a grammar, and an AST pass that resolves same-file callees to
real uids. Imports the `_go_uids` leaf only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from ..types import EvidenceSignal, GraphEdge, GraphNode
from ._go_receivers import GoFileTypes, GoType, GoValues, operand_type, scope_types_cached
from ._go_uids import (
    _GO_BUILTIN_TYPES,
    EXTRACTOR_ID,
    GO_BUILTIN_FUNCTIONS,
    _emit_type_relation,
    _find_field,
    _node_text,
    _parse_receiver,
    _walk_type_text,
    func_uid,
    method_uid,
    package_symbol_stub,
)
from .md_links import ExtractionResult

_CALL_RE = re.compile(r"\b(?P<lhs>[A-Za-z_][\w]*)\.(?P<name>[A-Z][\w]*)\s*\(")
SAME_FILE_CONFIDENCE = 0.9
PACKAGE_CALL_CONFIDENCE = 0.8
SAME_PACKAGE_CONFIDENCE = 0.7
TYPED_RECEIVER_CONFIDENCE = 0.8


def _walk_calls_regex(
    content: str,
    *,
    module_uid_str: str,
    result: ExtractionResult,
) -> None:
    seen: set[str] = set()
    for match in _CALL_RE.finditer(content):
        lhs = match.group("lhs")
        name = match.group("name")
        target = f"code:external:{lhs}.{name}"
        if target in seen:
            continue
        seen.add(target)
        result.nodes.append(
            GraphNode(
                uid=target,
                kind="code:external",
                label=f"{lhs}.{name}",
                lang="go",
                metadata={"extractor": EXTRACTOR_ID, "external_kind": "go_call"},
            )
        )
        result.edges.append(
            GraphEdge(
                source_uid=module_uid_str,
                target_uid=target,
                edge_type="calls",
                extractor=EXTRACTOR_ID,
                confidence=0.5,
            )
        )


def _walk_composite_constructs(
    node: Any,
    content_bytes: bytes,
    *,
    path: str,
    module_uid_str: str,
    result: ExtractionResult,
) -> None:
    type_node = _find_field(node, "type")
    if type_node is None:
        return
    target_label = _walk_type_text(type_node, content_bytes)
    _emit_type_relation(
        source_uid=module_uid_str,
        target_label=target_label,
        edge_type="constructs",
        path=path,
        extractor_id=EXTRACTOR_ID,
        result=result,
        confidence=0.7,
        evidence_signal="go_composite_literal",
    )


def _parse_receiver_var_type(receiver_node: Any, content_bytes: bytes) -> tuple[str, str]:
    if receiver_node is None:
        return "", ""
    text = _node_text(receiver_node, content_bytes).strip().strip("()")
    recv_type = _parse_receiver(text)
    parts = text.split()
    recv_var = parts[0] if parts and parts[0] != "*" else ""
    return recv_var, recv_type


def _collect_local_callables(
    root: Any, content_bytes: bytes, path: str
) -> tuple[dict[str, str], dict[tuple[str, str], str]]:
    """Pre-pass: same-file `name → func_uid` and `(recv_type, name) → method_uid`.

    Go allows forward references, so every callable must be collected
    before the call walk (mirrors the shell extractor's pass 1).
    """
    funcs: dict[str, str] = {}
    methods: dict[tuple[str, str], str] = {}
    stack = [root]
    while stack:
        node = stack.pop()
        if node.type == "function_declaration":
            name_node = _find_field(node, "name")
            if name_node is not None:
                name = _node_text(name_node, content_bytes)
                if name:
                    funcs[name] = func_uid(path, name)
        elif node.type == "method_declaration":
            name_node = _find_field(node, "name")
            recv_node = _find_field(node, "receiver")
            if name_node is not None and recv_node is not None:
                name = _node_text(name_node, content_bytes)
                _, recv_type = _parse_receiver_var_type(recv_node, content_bytes)
                if name and recv_type:
                    methods[(recv_type, name)] = method_uid(path, recv_type, name)
        stack.extend(node.children)
    return funcs, methods


def _enclosing_go_scope(node: Any, content_bytes: bytes, path: str) -> GoScope:
    cur = node.parent
    while cur is not None:
        if cur.type == "function_declaration":
            name_node = _find_field(cur, "name")
            name = _node_text(name_node, content_bytes) if name_node is not None else ""
            return GoScope(func_uid(path, name) if name else None, "", "", cur)
        if cur.type == "method_declaration":
            name_node = _find_field(cur, "name")
            recv_node = _find_field(cur, "receiver")
            name = _node_text(name_node, content_bytes) if name_node is not None else ""
            recv_var, recv_type = _parse_receiver_var_type(recv_node, content_bytes)
            uid = method_uid(path, recv_type, name) if (name and recv_type) else None
            return GoScope(uid, recv_var, recv_type, cur)
        cur = cur.parent
    return GoScope(None, "", "", None)


@dataclass(frozen=True)
class GoScope:
    uid: str | None
    receiver_var: str
    receiver_type: str
    declaration: Any


@dataclass(frozen=True)
class GoCallTarget:
    uid: str
    confidence: float
    signal: str


def _bound_names(declaration: Any, content_bytes: bytes) -> set[str]:
    """Every name a function binds locally: params, results, `:=`, `var`, range vars, closures."""
    names: set[str] = set()
    stack = [declaration]
    while stack:
        node = stack.pop()
        if node.type in _NAME_FIELD_BINDERS:
            names.update(
                _node_text(child, content_bytes) for child in node.children_by_field_name("name")
            )
        elif node.type in _LEFT_SIDE_BINDERS:
            left = _find_field(node, "left")
            names.update(_identifier_texts(left, content_bytes))
        elif node.type == "type_switch_statement":
            # `switch cause := err.(type)` binds `cause` in every case.
            names.update(_identifier_texts(_find_field(node, "alias"), content_bytes))
        stack.extend(node.children)
    if declaration.type == "method_declaration":
        names.update(receiver_type_arguments(declaration, content_bytes))
    return names


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


_NAME_FIELD_BINDERS = {
    "parameter_declaration",
    "variadic_parameter_declaration",
    "var_spec",
    "const_spec",
    "type_parameter_declaration",
}
_LEFT_SIDE_BINDERS = {"short_var_declaration", "range_clause"}


def _identifier_texts(node: Any, content_bytes: bytes) -> list[str]:
    if node is None:
        return []
    if node.type == "identifier":
        return [_node_text(node, content_bytes)]
    return [_node_text(c, content_bytes) for c in node.children if c.type == "identifier"]


def _walk_go_calls_ast(
    root: Any,
    content_bytes: bytes,
    *,
    path: str,
    directory: str,
    module_uid_str: str,
    imports: dict[str, tuple[str, str | None]],
    known: GoFileTypes,
    result: ExtractionResult,
) -> list[tuple[str, int]]:
    """Emit `calls` edges sourced at the enclosing func/method; return unimported receivers.

    Same-file callees resolve here at 0.9. A bare call to a function defined in
    another file of the package, and `pkg.Func()` through an import, become a
    `gopkg` stub the linker binds to the one definition (or a library stub
    keyed by import path). A method call on a value resolves where the source
    spells the value's type (`_go_receivers`); builtins and other values emit
    nothing.
    """
    local_funcs, local_methods = _collect_local_callables(root, content_bytes, path)
    bound_by_scope: dict[tuple[int, int], set[str]] = {}
    typed_by_scope: dict[tuple[int, int], dict[str, GoType]] = {}
    seen: set[tuple[str, str]] = set()
    unimported: dict[str, int] = {}
    for call in _iter_calls(root):
        fn = _find_field(call, "function")
        if fn is None:
            continue
        scope = _enclosing_go_scope(call, content_bytes, path)
        bound = _scope_bindings(scope, content_bytes, bound_by_scope)
        values = GoValues(
            scope_types_cached(
                scope.declaration, content_bytes, directory, imports, known, typed_by_scope
            ),
            known,
            directory,
            imports,
        )
        target = _call_target(
            fn, scope, bound, content_bytes, directory, imports, local_funcs, local_methods, values
        )
        src = scope.uid or module_uid_str
        if target is None:
            receiver = _unimported_receiver(
                fn, scope, bound, values, imports, local_funcs, content_bytes
            )
            if receiver:
                unimported.setdefault(receiver, call.start_point[0] + 1)
            continue
        if target.uid == src or (src, target.uid) in seen:
            continue
        seen.add((src, target.uid))
        result.edges.append(
            GraphEdge(
                source_uid=src,
                target_uid=target.uid,
                edge_type="calls",
                extractor=EXTRACTOR_ID,
                confidence=target.confidence,
                source_span=f"{path}:{call.start_point[0] + 1}",
                evidence=(EvidenceSignal(target.signal, target.confidence),),
            )
        )
    return sorted(unimported.items(), key=lambda item: (item[1], item[0]))


def _unimported_receiver(
    fn: Any,
    scope: GoScope,
    bound: set[str],
    values: GoValues,
    imports: dict[str, tuple[str, str | None]],
    local_funcs: dict[str, str],
    content_bytes: bytes,
) -> str:
    # `strings.ToUpper()` with no `import "strings"`: a candidate only — a
    # package-level `var db` in another file looks the same, so the undefined
    # report checks the whole package before naming it.
    if fn.type != "selector_expression":
        return ""
    operand = _find_field(fn, "operand")
    if operand is None or operand.type != "identifier":
        return ""
    name = _node_text(operand, content_bytes)
    if not name[:1].islower() or name == scope.receiver_var:
        return ""
    if name in bound or name in imports or name in values.typed or name in local_funcs:
        return ""
    return name


def _iter_calls(root: Any) -> list[Any]:
    calls: list[Any] = []
    stack = [root]
    while stack:
        node = stack.pop()
        if node.type == "call_expression":
            calls.append(node)
        stack.extend(node.children)
    return calls


def _scope_bindings(
    scope: GoScope, content_bytes: bytes, cache: dict[tuple[int, int], set[str]]
) -> set[str]:
    if scope.declaration is None:
        return set()
    key = (scope.declaration.start_byte, scope.declaration.end_byte)
    if key not in cache:
        cache[key] = _bound_names(scope.declaration, content_bytes)
    return cache[key]


def _call_target(
    fn: Any,
    scope: GoScope,
    bound: set[str],
    content_bytes: bytes,
    directory: str,
    imports: dict[str, tuple[str, str | None]],
    local_funcs: dict[str, str],
    local_methods: dict[tuple[str, str], str],
    values: GoValues | None = None,
) -> GoCallTarget | None:
    if fn.type == "identifier":
        name = _node_text(fn, content_bytes)
        if name in local_funcs:
            return GoCallTarget(local_funcs[name], SAME_FILE_CONFIDENCE, "go_same_scope")
        if not name or name in GO_BUILTIN_FUNCTIONS or name in _GO_BUILTIN_TYPES or name in bound:
            return None
        return GoCallTarget(
            package_symbol_stub(directory, name), SAME_PACKAGE_CONFIDENCE, "go_same_package"
        )
    if fn.type != "selector_expression":
        return None
    operand, field = _find_field(fn, "operand"), _find_field(fn, "field")
    if operand is None or field is None:
        return None
    if operand.type != "identifier":
        if values is None:
            return None
        receiver = operand_type(
            operand, scope.receiver_var, scope.receiver_type, content_bytes, values
        )
        if receiver is None:
            return None
        member = _node_text(field, content_bytes)
        return GoCallTarget(receiver.member(member), TYPED_RECEIVER_CONFIDENCE, "go_typed_receiver")
    base, member = _node_text(operand, content_bytes), _node_text(field, content_bytes)
    if scope.receiver_var and base == scope.receiver_var:
        known = local_methods.get((scope.receiver_type, member))
        if known:
            return GoCallTarget(known, SAME_FILE_CONFIDENCE, "go_receiver_method")
        stub = package_symbol_stub(directory, f"{scope.receiver_type}.{member}")
        return GoCallTarget(stub, SAME_PACKAGE_CONFIDENCE, "go_receiver_method")
    if values is not None and base in values.typed:
        target = values.typed[base].member(member)
        return GoCallTarget(target, TYPED_RECEIVER_CONFIDENCE, "go_typed_receiver")
    if base in bound or base not in imports:
        return None
    import_path, package_dir = imports[base]
    stub = (
        package_symbol_stub(package_dir, member)
        if package_dir
        else f"code:external:{import_path}:{member}"
    )
    return GoCallTarget(stub, PACKAGE_CALL_CONFIDENCE, "go_package_call")
