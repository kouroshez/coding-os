"""graph_os — Go function and method declarations.

Emits `code:function` / `code:method` nodes plus their parameter and return type
edges from the tree-sitter AST. Imports the `_go_uids` leaf only.
"""

from __future__ import annotations

from typing import Any

from ..types import EvidenceSignal, GraphEdge, GraphNode
from ._go_uids import (
    EXTRACTOR_ID,
    _classify_test_func,
    _emit_type_relation,
    _find_field,
    _node_text,
    _parse_receiver,
    _walk_type_text,
    class_uid,
    func_uid,
    method_uid,
)
from .md_links import ExtractionResult


def _emit_func_node(
    name: str,
    line: int,
    *,
    path: str,
    normalised: str,
    receiver_type: str,
    is_init: bool,
    test_kind: str | None,
    has_generics: bool,
    module_uid_str: str,
    result: ExtractionResult,
    seen: set[str],
) -> str | None:
    if receiver_type:
        uid = method_uid(path, receiver_type, name)
        kind = "code:method"
        label = f"{receiver_type}.{name}"
    else:
        uid = func_uid(path, name)
        kind = "code:function"
        label = name
    if uid in seen:
        return None
    seen.add(uid)

    metadata: dict[str, Any] = {
        "extractor": EXTRACTOR_ID,
        "receiver": receiver_type or "",
    }
    if is_init:
        metadata["init"] = True
    if test_kind:
        metadata["test_kind"] = test_kind
    if has_generics:
        metadata["generic"] = True

    result.nodes.append(
        GraphNode(
            uid=uid,
            kind=kind,
            label=label,
            file_path=normalised,
            start_line=line,
            lang="go",
            metadata=metadata,
        )
    )
    result.edges.append(
        GraphEdge(
            source_uid=module_uid_str,
            target_uid=uid,
            edge_type="contains",
            extractor=EXTRACTOR_ID,
            confidence=1.0,
        )
    )
    return uid


def _walk_function_decl(
    node: Any,
    content_bytes: bytes,
    *,
    path: str,
    normalised: str,
    module_uid_str: str,
    result: ExtractionResult,
    seen: set[str],
) -> None:
    name_node = _find_field(node, "name")
    if name_node is None:
        return
    name = _node_text(name_node, content_bytes)
    type_params = _find_field(node, "type_parameters")
    params_node = _find_field(node, "parameters")
    result_node = _find_field(node, "result")
    line = node.start_point[0] + 1
    is_init = name == "init"
    test_kind = _classify_test_func(name, normalised)
    uid = _emit_func_node(
        name=name,
        line=line,
        path=path,
        normalised=normalised,
        receiver_type="",
        is_init=is_init,
        test_kind=test_kind,
        has_generics=type_params is not None,
        module_uid_str=module_uid_str,
        result=result,
        seen=seen,
    )
    if uid is None:
        return
    _emit_param_and_return_edges(
        uid,
        params_node,
        result_node,
        content_bytes,
        path=path,
        result=result,
    )
    if test_kind:
        result.edges.append(
            GraphEdge(
                source_uid=module_uid_str,
                target_uid=f"code:external:test:{name}",
                edge_type="handles_test",
                extractor=EXTRACTOR_ID,
                confidence=1.0,
                evidence=(EvidenceSignal(test_kind, 1.0),),
            )
        )


def _walk_method_decl(
    node: Any,
    content_bytes: bytes,
    *,
    path: str,
    normalised: str,
    module_uid_str: str,
    result: ExtractionResult,
    seen: set[str],
) -> None:
    receiver_node = _find_field(node, "receiver")
    name_node = _find_field(node, "name")
    if name_node is None:
        return
    name = _node_text(name_node, content_bytes)
    receiver_text = _node_text(receiver_node, content_bytes) if receiver_node else ""
    receiver_text = receiver_text.strip("()")
    receiver_type = _parse_receiver(receiver_text)
    params_node = _find_field(node, "parameters")
    result_node = _find_field(node, "result")
    line = node.start_point[0] + 1
    uid = _emit_func_node(
        name=name,
        line=line,
        path=path,
        normalised=normalised,
        receiver_type=receiver_type,
        is_init=False,
        test_kind=None,
        has_generics="[" in receiver_text,
        module_uid_str=module_uid_str,
        result=result,
        seen=seen,
    )
    if uid is None:
        return
    if receiver_type:
        result.edges.append(
            GraphEdge(
                source_uid=class_uid(path, receiver_type),
                target_uid=uid,
                edge_type="contains",
                extractor=EXTRACTOR_ID,
                confidence=0.9,
                evidence=(EvidenceSignal("method_receiver", 0.9),),
            )
        )
    _emit_param_and_return_edges(
        uid,
        params_node,
        result_node,
        content_bytes,
        path=path,
        result=result,
    )


def _emit_param_and_return_edges(
    func_uid_str: str,
    params_node: Any,
    result_node: Any,
    content_bytes: bytes,
    *,
    path: str,
    result: ExtractionResult,
) -> None:
    if params_node is not None:
        for child in params_node.children:
            if child.type in ("parameter_declaration", "variadic_parameter_declaration"):
                type_field = _find_field(child, "type")
                if type_field is not None:
                    _emit_type_relation(
                        source_uid=func_uid_str,
                        target_label=_walk_type_text(type_field, content_bytes),
                        edge_type="has_param_type",
                        path=path,
                        extractor_id=EXTRACTOR_ID,
                        result=result,
                        confidence=0.85,
                        evidence_signal="go_param",
                    )
    if result_node is not None:
        if result_node.type == "parameter_list":
            for child in result_node.children:
                if child.type in ("parameter_declaration", "variadic_parameter_declaration"):
                    type_field = _find_field(child, "type")
                    if type_field is not None:
                        _emit_type_relation(
                            source_uid=func_uid_str,
                            target_label=_walk_type_text(type_field, content_bytes),
                            edge_type="returns_type",
                            path=path,
                            extractor_id=EXTRACTOR_ID,
                            result=result,
                            confidence=0.85,
                            evidence_signal="go_return",
                        )
        else:
            _emit_type_relation(
                source_uid=func_uid_str,
                target_label=_walk_type_text(result_node, content_bytes),
                edge_type="returns_type",
                path=path,
                extractor_id=EXTRACTOR_ID,
                result=result,
                confidence=0.85,
                evidence_signal="go_return",
            )
