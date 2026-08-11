"""Declaration pass over a parsed TypeScript / TSX tree.

Runs before the call pass so `local_names` is complete when calls and type
annotations resolve — a param type naming a class declared later in the file
still binds to the real local uid.
"""

from __future__ import annotations

from typing import Any

from ..types import EvidenceSignal, GraphEdge, GraphNode
from ._ts_nodes import (
    _ts_component_meta,
    _ts_decorator_name,
    _ts_emit_type_edges,
    _ts_line,
    _ts_name,
    _ts_resolve_type,
)
from ._ts_uids import (
    EXTRACTOR_ID_TS,
    _ts_method_uid,
    class_uid,
    function_uid,
    interface_uid,
)
from .md_links import ExtractionResult


def _emit_ts_class(
    cls: Any,
    *,
    path: str,
    module_uid_: str,
    lang: str,
    imported_names: dict[str, str],
    local_names: dict[str, str],
    methods_by_class: dict[str, dict[str, str]],
    pending_types: list[tuple[str, str, str, int]],
    result: ExtractionResult,
) -> None:
    """Emit one class node plus its decorator, heritage, and method edges."""
    name = _ts_name(cls)
    if not name:
        return
    cuid = class_uid(path, name)
    result.nodes.append(
        GraphNode(
            uid=cuid,
            kind="code:class",
            label=name,
            file_path=path,
            start_line=_ts_line(cls),
            signature=f"class {name}",
            lang=lang,
            metadata={"extractor": EXTRACTOR_ID_TS},
        )
    )
    local_names[name] = cuid
    result.edges.append(
        GraphEdge(
            source_uid=module_uid_,
            target_uid=cuid,
            edge_type="contains",
            extractor=EXTRACTOR_ID_TS,
            confidence=1.0,
        )
    )
    # Decorators may be children of the class OR of the wrapping
    # `export_statement` (`@Dec()\nexport class C`). Scan both.
    _dec_nodes = list(cls.children)
    if cls.parent is not None and cls.parent.type == "export_statement":
        _dec_nodes += list(cls.parent.children)
    _seen_dec: set[str] = set()
    for dec in _dec_nodes:
        if dec.type != "decorator":
            continue
        dname = _ts_decorator_name(dec)
        if dname and dname not in _seen_dec:
            _seen_dec.add(dname)
            result.edges.append(
                GraphEdge(
                    source_uid=cuid,
                    target_uid=_ts_resolve_type(dname, imported_names, local_names),
                    edge_type="is_decorated_by",
                    extractor=EXTRACTOR_ID_TS,
                    confidence=0.85,
                    source_span=f"{path}:{_ts_line(dec)}",
                )
            )
    heritage = next((c for c in cls.children if c.type == "class_heritage"), None)
    if heritage is not None:
        for clause in heritage.children:
            etype = (
                "inherits_from"
                if clause.type == "extends_clause"
                else ("implements" if clause.type == "implements_clause" else None)
            )
            if etype is None:
                continue
            for t in clause.children:
                if t.type in (
                    "identifier",
                    "type_identifier",
                    "member_expression",
                    "generic_type",
                ):
                    base = t.text.decode("utf-8", "replace")
                    result.edges.append(
                        GraphEdge(
                            source_uid=cuid,
                            target_uid=_ts_resolve_type(base, imported_names, local_names),
                            edge_type=etype,
                            extractor=EXTRACTOR_ID_TS,
                            confidence=0.8,
                            source_span=f"{path}:{_ts_line(clause)}",
                        )
                    )
    body = next((c for c in cls.children if c.type == "class_body"), None)
    if body is not None:
        for m in body.children:
            if m.type != "method_definition":
                continue
            mname = _ts_name(m)
            if not mname:
                continue
            muid = _ts_method_uid(path, name, mname)
            methods_by_class.setdefault(cuid, {})[mname] = muid
            result.nodes.append(
                GraphNode(
                    uid=muid,
                    kind="code:method",
                    label=mname,
                    file_path=path,
                    start_line=_ts_line(m),
                    signature=f"{name}.{mname}(…)",
                    lang=lang,
                    metadata={"extractor": EXTRACTOR_ID_TS},
                )
            )
            result.edges.append(
                GraphEdge(
                    source_uid=cuid,
                    target_uid=muid,
                    edge_type="contains",
                    extractor=EXTRACTOR_ID_TS,
                    confidence=1.0,
                )
            )
            for dec in m.children:
                if dec.type != "decorator":
                    continue
                dname = _ts_decorator_name(dec)
                if dname:
                    result.edges.append(
                        GraphEdge(
                            source_uid=muid,
                            target_uid=_ts_resolve_type(dname, imported_names, local_names),
                            edge_type="is_decorated_by",
                            extractor=EXTRACTOR_ID_TS,
                            confidence=0.85,
                            source_span=f"{path}:{_ts_line(dec)}",
                        )
                    )
            _ts_emit_type_edges(m, owner_uid=muid, path=path, pending=pending_types)


def _walk_ts_declarations(
    root: Any,
    *,
    path: str,
    module_uid_: str,
    lang: str,
    imported_names: dict[str, str],
    local_names: dict[str, str],
    result: ExtractionResult,
) -> dict[str, dict[str, str]]:
    """Emit declaration nodes + heritage/type/decorator edges; return class methods."""
    from ..tree_sitter_overlay import iter_nodes

    # GE: per-class method map so `this.method()` resolves to THIS class's
    # method instead of an unresolved stub (matters for class-heavy TS:
    # NestJS / Angular). Populated in the class-body method loop below.
    methods_by_class: dict[str, dict[str, str]] = {}
    # Deferred type-annotation edges — resolved after the declaration pass.
    pending_types: list[tuple[str, str, str, int]] = []

    # ---- Pass A: declarations (populate local_names before resolving calls) ----
    for fn in iter_nodes(root, {"function_declaration", "generator_function_declaration"}):
        name = _ts_name(fn)
        if not name:
            continue
        uid = function_uid(path, name)
        result.nodes.append(
            GraphNode(
                uid=uid,
                kind="code:function",
                label=name,
                file_path=path,
                start_line=_ts_line(fn),
                signature=f"function {name}(…)",
                lang=lang,
                metadata=_ts_component_meta(name, fn, lang),
            )
        )
        local_names[name] = uid
        result.edges.append(
            GraphEdge(
                source_uid=module_uid_,
                target_uid=uid,
                edge_type="contains",
                extractor=EXTRACTOR_ID_TS,
                confidence=1.0,
            )
        )
        _ts_emit_type_edges(fn, owner_uid=uid, path=path, pending=pending_types)

    for vd in iter_nodes(root, {"variable_declarator"}):
        val = vd.child_by_field_name("value")
        if val is None or val.type not in ("arrow_function", "function", "function_expression"):
            continue
        name = _ts_name(vd)
        if not name or name in local_names:
            continue
        uid = function_uid(path, name)
        _arrow_meta = _ts_component_meta(name, val, lang)
        _arrow_meta["arrow"] = True
        result.nodes.append(
            GraphNode(
                uid=uid,
                kind="code:function",
                label=name,
                file_path=path,
                start_line=_ts_line(vd),
                signature=f"const {name} = (…) =>",
                lang=lang,
                metadata=_arrow_meta,
            )
        )
        local_names[name] = uid
        result.edges.append(
            GraphEdge(
                source_uid=module_uid_,
                target_uid=uid,
                edge_type="contains",
                extractor=EXTRACTOR_ID_TS,
                confidence=1.0,
            )
        )
        _ts_emit_type_edges(val, owner_uid=uid, path=path, pending=pending_types)

    for it in iter_nodes(root, {"interface_declaration"}):
        name = _ts_name(it)
        if not name:
            continue
        uid = interface_uid(path, name)
        result.nodes.append(
            GraphNode(
                uid=uid,
                kind="code:interface",
                label=name,
                file_path=path,
                start_line=_ts_line(it),
                signature=f"interface {name}",
                lang=lang,
                metadata={"extractor": EXTRACTOR_ID_TS},
            )
        )
        local_names[name] = uid
        result.edges.append(
            GraphEdge(
                source_uid=module_uid_,
                target_uid=uid,
                edge_type="contains",
                extractor=EXTRACTOR_ID_TS,
                confidence=1.0,
            )
        )
        ext = next((c for c in it.children if c.type == "extends_type_clause"), None)
        if ext is not None:
            for t in ext.children:
                if t.type in ("type_identifier", "identifier", "generic_type"):
                    result.edges.append(
                        GraphEdge(
                            source_uid=uid,
                            target_uid=_ts_resolve_type(
                                t.text.decode("utf-8", "replace"), imported_names, local_names
                            ),
                            edge_type="extends",
                            extractor=EXTRACTOR_ID_TS,
                            confidence=0.8,
                            source_span=f"{path}:{_ts_line(ext)}",
                        )
                    )

    for ta in iter_nodes(root, {"type_alias_declaration"}):
        name = _ts_name(ta)
        if not name or name in local_names:
            continue
        uid = interface_uid(path, name)
        result.nodes.append(
            GraphNode(
                uid=uid,
                kind="code:interface",
                label=name,
                file_path=path,
                start_line=_ts_line(ta),
                signature=f"type {name}",
                lang=lang,
                metadata={"extractor": EXTRACTOR_ID_TS, "type_alias": True},
            )
        )
        local_names[name] = uid
        result.edges.append(
            GraphEdge(
                source_uid=module_uid_,
                target_uid=uid,
                edge_type="contains",
                extractor=EXTRACTOR_ID_TS,
                confidence=1.0,
            )
        )

    for cls in iter_nodes(root, {"class_declaration", "abstract_class_declaration"}):
        _emit_ts_class(
            cls,
            path=path,
            module_uid_=module_uid_,
            lang=lang,
            imported_names=imported_names,
            local_names=local_names,
            methods_by_class=methods_by_class,
            pending_types=pending_types,
            result=result,
        )

    # ---- enum / namespace declarations (queryable type-like nodes) ----
    for en in iter_nodes(root, {"enum_declaration"}):
        name = _ts_name(en)
        if not name or name in local_names:
            continue
        uid = class_uid(path, name)
        result.nodes.append(
            GraphNode(
                uid=uid,
                kind="code:class",
                label=name,
                file_path=path,
                start_line=_ts_line(en),
                signature=f"enum {name}",
                lang=lang,
                metadata={"extractor": EXTRACTOR_ID_TS, "ts_kind": "enum"},
            )
        )
        local_names[name] = uid
        result.edges.append(
            GraphEdge(
                source_uid=module_uid_,
                target_uid=uid,
                edge_type="contains",
                extractor=EXTRACTOR_ID_TS,
                confidence=1.0,
            )
        )

    for ns in iter_nodes(root, {"internal_module"}):
        name = _ts_name(ns)
        if not name or name in local_names:
            continue
        uid = class_uid(path, name)
        result.nodes.append(
            GraphNode(
                uid=uid,
                kind="code:class",
                label=name,
                file_path=path,
                start_line=_ts_line(ns),
                signature=f"namespace {name}",
                lang=lang,
                metadata={"extractor": EXTRACTOR_ID_TS, "ts_kind": "namespace"},
            )
        )
        local_names[name] = uid
        result.edges.append(
            GraphEdge(
                source_uid=module_uid_,
                target_uid=uid,
                edge_type="contains",
                extractor=EXTRACTOR_ID_TS,
                confidence=1.0,
            )
        )

    # ---- resolve deferred type edges (local_names now complete) ----
    for owner_uid, tname, etype, line in pending_types:
        target = _ts_resolve_type(tname, imported_names, local_names)
        conf = (
            0.8 if target.startswith(("code:class:", "code:interface:", "code:function:")) else 0.5
        )
        result.edges.append(
            GraphEdge(
                source_uid=owner_uid,
                target_uid=target,
                edge_type=etype,
                extractor=EXTRACTOR_ID_TS,
                confidence=conf,
                source_span=f"{path}:{line}",
                evidence=(EvidenceSignal("ts_annotation", conf),),
            )
        )

    return methods_by_class
