"""graph_os — Go type declarations: structs, interfaces, aliases and generics.

Emits `code:class` nodes plus the embedding (`inherits_from`) and field
(`field_of_type`) edges Go expresses through anonymous members, and one abstract
`code:method` node per method an interface declares. Imports the `_go_uids` leaf
and `_go_symbols` for the signature edges a method shares with a function.
"""

from __future__ import annotations

from typing import Any

from ..types import GraphEdge, GraphNode
from ._fingerprint import body_fields
from ._go_symbols import _emit_param_and_return_edges
from ._go_uids import (
    _GO_BUILTIN_TYPES,
    EXTRACTOR_ID,
    _emit_type_relation,
    _find_child,
    _find_field,
    _guess_type_kind,
    _node_text,
    _walk_type_text,
    arity,
    class_uid,
    method_uid,
)
from .md_links import ExtractionResult


def _walk_type_decl(
    node: Any,
    content_bytes: bytes,
    *,
    path: str,
    normalised: str,
    module_uid_str: str,
    result: ExtractionResult,
    seen: set[str],
) -> None:
    for child in node.children:
        if child.type not in ("type_spec", "type_alias"):
            continue
        name_node = _find_field(child, "name")
        type_node = _find_field(child, "type")
        if name_node is None:
            continue
        name = _node_text(name_node, content_bytes)
        uid = class_uid(path, name)
        if uid in seen:
            continue
        seen.add(uid)
        type_params = _find_field(child, "type_parameters")
        line = child.start_point[0] + 1
        go_kind = "alias" if child.type == "type_alias" else _guess_type_kind(type_node)
        metadata: dict[str, Any] = {
            "extractor": EXTRACTOR_ID,
            "go_kind": go_kind,
        }
        if type_params is not None:
            metadata["generic"] = True
        if go_kind == "interface":
            metadata.update(_embedded_builtins(type_node, content_bytes))
        result.nodes.append(
            GraphNode(
                uid=uid,
                kind="code:class",
                label=name,
                file_path=normalised,
                start_line=line,
                **body_fields(child),
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
        if type_node is not None:
            if type_node.type == "struct_type":
                _emit_struct_relations(uid, type_node, content_bytes, path=path, result=result)
            elif type_node.type == "interface_type":
                _emit_interface_relations(
                    uid,
                    name,
                    type_node,
                    content_bytes,
                    path=path,
                    normalised=normalised,
                    result=result,
                    seen=seen,
                )
            elif child.type == "type_alias":
                # alias to another named type
                _emit_type_relation(
                    source_uid=uid,
                    target_label=_walk_type_text(type_node, content_bytes),
                    edge_type="inherits_from",
                    path=path,
                    extractor_id=EXTRACTOR_ID,
                    result=result,
                    confidence=0.95,
                    evidence_signal="go_alias",
                )


def _emit_struct_relations(
    type_uid: str,
    struct_node: Any,
    content_bytes: bytes,
    *,
    path: str,
    result: ExtractionResult,
) -> None:
    field_list = _find_child(struct_node, "field_declaration_list")
    if field_list is None:
        return
    for field in field_list.children:
        if field.type != "field_declaration":
            continue
        type_field = _find_field(field, "type")
        name_field = _find_field(field, "name")
        if type_field is None:
            continue
        if name_field is None:
            # Embedded field — type only, no name.
            _emit_type_relation(
                source_uid=type_uid,
                target_label=_walk_type_text(type_field, content_bytes),
                edge_type="inherits_from",
                path=path,
                extractor_id=EXTRACTOR_ID,
                result=result,
                confidence=0.95,
                evidence_signal="go_embedded_field",
            )
        else:
            _emit_type_relation(
                source_uid=type_uid,
                target_label=_walk_type_text(type_field, content_bytes),
                edge_type="field_of_type",
                path=path,
                extractor_id=EXTRACTOR_ID,
                result=result,
                confidence=0.85,
                evidence_signal="go_struct_field",
            )


def _emit_interface_relations(
    type_uid: str,
    iface_name: str,
    iface_node: Any,
    content_bytes: bytes,
    *,
    path: str,
    normalised: str,
    result: ExtractionResult,
    seen: set[str],
) -> None:
    for child in iface_node.children:
        # method_elem — method signature inside the interface.
        # type_elem  — embedded type or type constraint (Go 1.18+).
        if child.type == "method_elem":
            _emit_interface_method(
                type_uid,
                iface_name,
                child,
                content_bytes,
                path=path,
                normalised=normalised,
                result=result,
                seen=seen,
            )
        elif child.type == "type_elem":
            for grand in child.children:
                txt = _walk_type_text(grand, content_bytes)
                if not txt or txt in {"|", "~"}:
                    continue
                _emit_type_relation(
                    source_uid=type_uid,
                    target_label=txt,
                    edge_type="inherits_from",
                    path=path,
                    extractor_id=EXTRACTOR_ID,
                    result=result,
                    confidence=0.9,
                    evidence_signal="go_iface_embed",
                )


def _embedded_builtins(iface_node: Any, content_bytes: bytes) -> dict[str, bool]:
    # `error` adds Error() to the method set; a union, `~T` or other builtin makes
    # the interface a constraint, which no type implements by its methods.
    found: dict[str, bool] = {}
    for child in iface_node.children:
        if child.type != "type_elem":
            continue
        parts = [part for part in child.children if part.type != "|"]
        texts = {_node_text(part, content_bytes) for part in parts}
        if texts == {"error"}:
            found["embeds_error"] = True
        elif (
            len(parts) > 1
            or any(part.type == "negated_type" for part in parts)
            or texts & (_GO_BUILTIN_TYPES - {"any"})
        ):
            found["type_set"] = True
    return found


def _emit_interface_method(
    iface_uid: str,
    iface_name: str,
    method_node: Any,
    content_bytes: bytes,
    *,
    path: str,
    normalised: str,
    result: ExtractionResult,
    seen: set[str],
) -> None:
    name_node = _find_field(method_node, "name")
    if name_node is None:
        return
    name = _node_text(name_node, content_bytes)
    uid = method_uid(path, iface_name, name)
    if uid in seen:
        return
    seen.add(uid)
    params_node = _find_field(method_node, "parameters")
    result_node = _find_field(method_node, "result")
    result.nodes.append(
        GraphNode(
            uid=uid,
            kind="code:method",
            label=f"{iface_name}.{name}",
            file_path=normalised,
            start_line=method_node.start_point[0] + 1,
            end_line=method_node.end_point[0] + 1,
            signature=" ".join(_node_text(method_node, content_bytes).split()),
            lang="go",
            metadata={
                "extractor": EXTRACTOR_ID,
                "receiver": iface_name,
                "abstract": True,
                "arity": arity(params_node, result_node),
            },
        )
    )
    result.edges.append(
        GraphEdge(
            source_uid=iface_uid,
            target_uid=uid,
            edge_type="contains",
            extractor=EXTRACTOR_ID,
            confidence=1.0,
        )
    )
    _emit_param_and_return_edges(
        uid, params_node, result_node, content_bytes, path=path, result=result
    )
