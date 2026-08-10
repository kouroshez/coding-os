"""graph_os — Go call and construction edges.

Two paths that coexist: a regex pass for qualified `pkg.Func(...)` receivers that
survives without a grammar, and an AST pass that resolves same-file callees to
real uids. Imports the `_go_uids` leaf only.
"""

from __future__ import annotations

import re
from typing import Any

from ..types import EvidenceSignal, GraphEdge, GraphNode
from ._go_uids import (
    EXTRACTOR_ID,
    _emit_type_relation,
    _find_field,
    _node_text,
    _parse_receiver,
    _walk_type_text,
    func_uid,
    method_uid,
)
from .md_links import ExtractionResult

_CALL_RE = re.compile(r"\b(?P<lhs>[A-Za-z_][\w]*)\.(?P<name>[A-Z][\w]*)\s*\(")


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


def _enclosing_go_scope(node: Any, content_bytes: bytes, path: str) -> tuple[str | None, str, str]:
    """Return (enclosing_uid, receiver_var, receiver_type) for a call node."""
    cur = node.parent
    while cur is not None:
        if cur.type == "function_declaration":
            name_node = _find_field(cur, "name")
            name = _node_text(name_node, content_bytes) if name_node is not None else ""
            return (func_uid(path, name) if name else None, "", "")
        if cur.type == "method_declaration":
            name_node = _find_field(cur, "name")
            recv_node = _find_field(cur, "receiver")
            name = _node_text(name_node, content_bytes) if name_node is not None else ""
            recv_var, recv_type = _parse_receiver_var_type(recv_node, content_bytes)
            uid = method_uid(path, recv_type, name) if (name and recv_type) else None
            return (uid, recv_var, recv_type)
        cur = cur.parent
    return (None, "", "")


def _walk_go_calls_ast(
    root: Any,
    content_bytes: bytes,
    *,
    path: str,
    normalised: str,
    module_uid_str: str,
    result: ExtractionResult,
) -> None:
    """Emit same-file resolved `calls` edges (Python `same_scope` parity).

    Two resolvable shapes get a confidence-0.9 edge sourced at the
    enclosing func/method:
      - bare `B()` where B is a same-file top-level function;
      - `r.M()` where r is the enclosing method's receiver var and M is a
        method on that same receiver type.
    Cross-package / unresolved calls stay with the regex pass (module
    scope, conf 0.5) — this pass only adds the high-confidence local graph.
    """
    local_funcs, local_methods = _collect_local_callables(root, content_bytes, path)
    if not local_funcs and not local_methods:
        return
    seen: set[tuple[str, str]] = set()
    stack = [root]
    while stack:
        node = stack.pop()
        if node.type == "call_expression":
            fn = _find_field(node, "function")
            if fn is not None:
                src_uid, recv_var, recv_type = _enclosing_go_scope(node, content_bytes, path)
                src = src_uid or module_uid_str
                target: str | None = None
                signal = "go_same_scope"
                if fn.type == "identifier":
                    target = local_funcs.get(_node_text(fn, content_bytes))
                elif fn.type == "selector_expression":
                    operand = _find_field(fn, "operand")
                    field = _find_field(fn, "field")
                    base = _node_text(operand, content_bytes) if operand is not None else ""
                    method_name = _node_text(field, content_bytes) if field is not None else ""
                    if base and base == recv_var and method_name:
                        target = local_methods.get((recv_type, method_name))
                        signal = "go_receiver_method"
                if target and target != src:
                    key = (src, target)
                    if key not in seen:
                        seen.add(key)
                        result.edges.append(
                            GraphEdge(
                                source_uid=src,
                                target_uid=target,
                                edge_type="calls",
                                extractor=EXTRACTOR_ID,
                                confidence=0.9,
                                source_span=f"{normalised}:{node.start_point[0] + 1}",
                                evidence=(EvidenceSignal(signal, 0.9),),
                            )
                        )
        stack.extend(node.children)
