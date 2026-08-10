"""graph_os — PHP declaration walker: nodes plus heritage / type / attribute edges.

Emits classes, interfaces, traits, functions, methods, properties, constants and
`use` imports, deferring name resolution until the whole file has been seen.
Imports only the `_php_uids` leaf, never a walker sibling.
"""

from __future__ import annotations

from typing import Any

from ..types import EvidenceSignal, GraphEdge, GraphNode
from ._php_uids import (
    EXTRACTOR_ID,
    _find_field,
    _node_text,
    _php_attr_names,
    _php_collect_type_names,
    _php_short,
    _resolve_php_type,
    class_uid,
    func_uid,
    interface_uid,
    method_uid,
    variable_uid,
)
from .md_links import ExtractionResult


def _walk_php_symbols(
    root: Any,
    content_bytes: bytes,
    *,
    path: str,
    normalised: str,
    module_uid_str: str,
    result: ExtractionResult,
) -> tuple[str, dict[str, str], dict[str, str]]:
    """Emit declarations + edges. Returns (namespace, local_names, imported)."""
    namespace = ""
    local_names: dict[str, str] = {}
    imported: dict[str, str] = {}
    pending_types: list[tuple[str, str, str]] = []  # (owner_uid, type_name, edge_type)
    pending_heritage: list[tuple[str, str, str]] = []  # (owner_uid, name, edge_type)
    pending_attrs: list[tuple[str, str]] = []  # (owner_uid, attr_name)

    def emit_type_edges(owner_uid: str, fn_node: Any) -> None:
        params = _find_field(fn_node, "parameters")
        if params is not None:
            for p in params.children:
                if p.type not in (
                    "simple_parameter",
                    "variadic_parameter",
                    "property_promotion_parameter",
                ):
                    continue
                type_node = _find_field(p, "type") or next(
                    (c for c in p.children if c.type.endswith("_type")), None
                )
                for tname in _php_collect_type_names(type_node, content_bytes):
                    pending_types.append((owner_uid, tname, "has_param_type"))
                if p.type == "property_promotion_parameter":
                    _emit_promoted_property(owner_uid, p, type_node)
        rt = _find_field(fn_node, "return_type")
        for tname in _php_collect_type_names(rt, content_bytes):
            pending_types.append((owner_uid, tname, "returns_type"))

    def _emit_promoted_property(class_uid_str: str, param: Any, type_node: Any) -> None:
        var = next((c for c in param.children if c.type == "variable_name"), None)
        if var is None:
            return
        pname = _node_text(var, content_bytes).lstrip("$")
        # owner is the method; the property belongs to the enclosing class —
        # resolve it via the method uid prefix (…::Class.method → …::Class.prop).
        cls_prefix = class_uid_str.split("::")[0].replace("code:method:", "code:class:")
        cls_name = class_uid_str.split("::")[-1].split(".")[0]
        puid = variable_uid(path, f"{cls_name}.{pname}")
        result.nodes.append(
            GraphNode(
                uid=puid,
                kind="code:variable",
                label=pname,
                file_path=normalised,
                start_line=param.start_point[0] + 1,
                lang="php",
                metadata={"extractor": EXTRACTOR_ID, "php_kind": "promoted_property"},
            )
        )
        result.edges.append(
            GraphEdge(
                source_uid=f"{cls_prefix}::{cls_name}",
                target_uid=puid,
                edge_type="contains",
                extractor=EXTRACTOR_ID,
                confidence=1.0,
            )
        )
        for tname in _php_collect_type_names(type_node, content_bytes):
            pending_types.append((puid, tname, "field_of_type"))

    def emit_class(node: Any, kind: str) -> str:
        nm = _find_field(node, "name")
        name = _node_text(nm, content_bytes) if nm is not None else ""
        if not name:
            return ""
        is_iface = kind == "interface"
        uid = interface_uid(path, name) if is_iface else class_uid(path, name)
        node_kind = "code:interface" if is_iface else "code:class"
        meta: dict[str, Any] = {"extractor": EXTRACTOR_ID}
        if kind == "trait":
            meta["php_kind"] = "trait"
        result.nodes.append(
            GraphNode(
                uid=uid,
                kind=node_kind,
                label=name,
                file_path=normalised,
                start_line=node.start_point[0] + 1,
                lang="php",
                metadata=meta,
            )
        )
        local_names[name] = uid
        result.edges.append(
            GraphEdge(
                source_uid=module_uid_str,
                target_uid=uid,
                edge_type="contains",
                extractor=EXTRACTOR_ID,
                confidence=1.0,
            )
        )
        # extends
        base = _find_field(node, "base_clause") or next(
            (c for c in node.children if c.type == "base_clause"), None
        )
        if base is not None:
            for c in base.children:
                if c.type in ("name", "qualified_name"):
                    pending_heritage.append((uid, _node_text(c, content_bytes), "inherits_from"))
        # implements
        impl = next((c for c in node.children if c.type == "class_interface_clause"), None)
        if impl is not None:
            for c in impl.children:
                if c.type in ("name", "qualified_name"):
                    pending_heritage.append((uid, _node_text(c, content_bytes), "implements"))
        # attributes
        for c in node.children:
            if c.type == "attribute_list":
                for an in _php_attr_names(c, content_bytes):
                    pending_attrs.append((uid, an))
        # body: trait-use, properties, consts, methods
        body = next((c for c in node.children if c.type == "declaration_list"), None)
        if body is not None:
            for member in body.children:
                if member.type == "use_declaration":
                    for c in member.children:
                        if c.type in ("name", "qualified_name"):
                            pending_heritage.append(
                                (uid, _node_text(c, content_bytes), "uses_trait")
                            )
                elif member.type == "property_declaration":
                    emit_property(uid, name, member)
                elif member.type == "const_declaration":
                    emit_const(uid, name, member)
                elif member.type == "method_declaration":
                    emit_method(uid, name, member)
        return uid

    def emit_property(class_uid_str: str, class_name: str, node: Any) -> None:
        type_node = _find_field(node, "type") or next(
            (c for c in node.children if c.type.endswith("_type")), None
        )
        for el in node.children:
            if el.type != "property_element":
                continue
            nm = _find_field(el, "name") or next(
                (c for c in el.children if c.type == "variable_name"), None
            )
            pname = _node_text(nm, content_bytes).lstrip("$") if nm is not None else ""
            if not pname:
                continue
            puid = variable_uid(path, f"{class_name}.{pname}")
            result.nodes.append(
                GraphNode(
                    uid=puid,
                    kind="code:variable",
                    label=pname,
                    file_path=normalised,
                    start_line=el.start_point[0] + 1,
                    lang="php",
                    metadata={"extractor": EXTRACTOR_ID, "php_kind": "property"},
                )
            )
            result.edges.append(
                GraphEdge(
                    source_uid=class_uid_str,
                    target_uid=puid,
                    edge_type="contains",
                    extractor=EXTRACTOR_ID,
                    confidence=1.0,
                )
            )
            for tname in _php_collect_type_names(type_node, content_bytes):
                pending_types.append((puid, tname, "field_of_type"))

    def emit_const(class_uid_str: str, class_name: str, node: Any) -> None:
        for el in node.children:
            if el.type != "const_element":
                continue
            nm = next((c for c in el.children if c.type == "name"), None)
            cname = _node_text(nm, content_bytes) if nm is not None else ""
            if not cname:
                continue
            cuid = variable_uid(path, f"{class_name}.{cname}")
            result.nodes.append(
                GraphNode(
                    uid=cuid,
                    kind="code:variable",
                    label=cname,
                    file_path=normalised,
                    start_line=el.start_point[0] + 1,
                    lang="php",
                    metadata={"extractor": EXTRACTOR_ID, "php_kind": "const"},
                )
            )
            result.edges.append(
                GraphEdge(
                    source_uid=class_uid_str,
                    target_uid=cuid,
                    edge_type="contains",
                    extractor=EXTRACTOR_ID,
                    confidence=1.0,
                )
            )

    def emit_method(class_uid_str: str, class_name: str, node: Any) -> None:
        nm = _find_field(node, "name")
        name = _node_text(nm, content_bytes) if nm is not None else ""
        if not name:
            return
        uid = method_uid(path, class_name, name)
        result.nodes.append(
            GraphNode(
                uid=uid,
                kind="code:method",
                label=name,
                file_path=normalised,
                start_line=node.start_point[0] + 1,
                signature=f"{class_name}.{name}()",
                lang="php",
                metadata={"extractor": EXTRACTOR_ID},
            )
        )
        result.edges.append(
            GraphEdge(
                source_uid=class_uid_str,
                target_uid=uid,
                edge_type="contains",
                extractor=EXTRACTOR_ID,
                confidence=1.0,
            )
        )
        for c in node.children:
            if c.type == "attribute_list":
                for an in _php_attr_names(c, content_bytes):
                    pending_attrs.append((uid, an))
        emit_type_edges(uid, node)

    def emit_function(node: Any) -> None:
        nm = _find_field(node, "name")
        name = _node_text(nm, content_bytes) if nm is not None else ""
        if not name:
            return
        uid = func_uid(path, name)
        result.nodes.append(
            GraphNode(
                uid=uid,
                kind="code:function",
                label=name,
                file_path=normalised,
                start_line=node.start_point[0] + 1,
                signature=f"function {name}()",
                lang="php",
                metadata={"extractor": EXTRACTOR_ID},
            )
        )
        local_names[name] = uid
        result.edges.append(
            GraphEdge(
                source_uid=module_uid_str,
                target_uid=uid,
                edge_type="contains",
                extractor=EXTRACTOR_ID,
                confidence=1.0,
            )
        )
        emit_type_edges(uid, node)

    # Top-level walk (declarations only — nested funcs/classes are rare in PHP
    # and emit_class recurses into its own body).
    for node in _iter_top_level(root):
        t = node.type
        if t == "namespace_definition":
            nm = _find_field(node, "name")
            namespace = _node_text(nm, content_bytes).strip() if nm is not None else ""
        elif t == "namespace_use_declaration":
            _emit_use(node, content_bytes, module_uid_str, result, imported, normalised)
        elif t == "class_declaration":
            emit_class(node, "class")
        elif t == "interface_declaration":
            emit_class(node, "interface")
        elif t == "trait_declaration":
            emit_class(node, "trait")
        elif t == "function_definition":
            emit_function(node)

    # Resolve deferred heritage / type / attribute edges (local_names complete).
    for owner_uid, name, etype in pending_heritage:
        signal = "php_use_trait" if etype == "uses_trait" else f"php_{etype}"
        edge_type = "inherits_from" if etype in ("inherits_from", "uses_trait") else etype
        result.edges.append(
            GraphEdge(
                source_uid=owner_uid,
                target_uid=_resolve_php_type(name, local_names, imported),
                edge_type=edge_type,
                extractor=EXTRACTOR_ID,
                confidence=0.9 if etype != "implements" else 0.8,
                evidence=(EvidenceSignal(signal, 0.9),),
            )
        )
    for owner_uid, tname, etype in pending_types:
        target = _resolve_php_type(tname, local_names, imported)
        conf = 0.8 if target.startswith(("code:class:", "code:interface:")) else 0.5
        result.edges.append(
            GraphEdge(
                source_uid=owner_uid,
                target_uid=target,
                edge_type=etype,
                extractor=EXTRACTOR_ID,
                confidence=conf,
                evidence=(EvidenceSignal("php_type", conf),),
            )
        )
    for owner_uid, attr in pending_attrs:
        result.edges.append(
            GraphEdge(
                source_uid=owner_uid,
                target_uid=_resolve_php_type(attr, local_names, imported),
                edge_type="is_decorated_by",
                extractor=EXTRACTOR_ID,
                confidence=0.85,
                evidence=(EvidenceSignal("php_attribute", 0.85),),
            )
        )
    return namespace, local_names, imported


def _iter_top_level(root: Any) -> list[Any]:
    """Top-level declarations, descending through the program + namespace bodies."""
    out: list[Any] = []
    for child in root.children:
        out.append(child)
        if child.type == "namespace_definition":
            body = next((c for c in child.children if c.type == "compound_statement"), None)
            if body is not None:
                out.extend(body.children)
    return out


def _emit_use(
    node: Any,
    content_bytes: bytes,
    module_uid_str: str,
    result: ExtractionResult,
    imported: dict[str, str],
    normalised: str,
) -> None:
    # Grouped: `use App\Lib\{A, B as C};` → prefix namespace_name + namespace_use_group.
    prefix = ""
    group = next((c for c in node.children if c.type == "namespace_use_group"), None)
    if group is not None:
        pn = next((c for c in node.children if c.type == "namespace_name"), None)
        prefix = _node_text(pn, content_bytes).strip().rstrip("\\") if pn is not None else ""
        clauses = [c for c in group.children if c.type == "namespace_use_clause"]
    else:
        clauses = [c for c in node.children if c.type == "namespace_use_clause"]
    for clause in clauses:
        _emit_use_clause(clause, content_bytes, module_uid_str, result, imported, prefix)


def _emit_use_clause(
    clause: Any,
    content_bytes: bytes,
    module_uid_str: str,
    result: ExtractionResult,
    imported: dict[str, str],
    prefix: str,
) -> None:
    name_node = next(
        (c for c in clause.children if c.type in ("qualified_name", "namespace_name", "name")), None
    )
    if name_node is None:
        return
    raw = _node_text(name_node, content_bytes).strip().lstrip("\\")
    fqn = f"{prefix}\\{raw}" if prefix else raw
    alias_node = _find_field(clause, "alias")
    alias = _node_text(alias_node, content_bytes).strip() if alias_node is not None else ""
    local = alias or _php_short(fqn)
    imported[local] = fqn
    target = f"code:external:{fqn}"
    meta: dict[str, Any] = {"extractor": EXTRACTOR_ID, "external_kind": "php_use"}
    if alias:
        meta["alias"] = alias
    result.nodes.append(
        GraphNode(uid=target, kind="code:external", label=fqn, lang="php", metadata=meta)
    )
    result.edges.append(
        GraphEdge(
            source_uid=module_uid_str,
            target_uid=target,
            edge_type="imports",
            extractor=EXTRACTOR_ID,
            confidence=0.95,
            evidence=(EvidenceSignal("php_use", 0.95),),
        )
    )
