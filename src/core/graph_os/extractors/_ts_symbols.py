"""AST-accurate symbol and edge walk over a parsed TypeScript / TSX tree.

The parity path: emits the same node/edge shapes as the regex fallback but
scope-accurate — calls sourced at the enclosing function/method, heritage and
type annotations resolved against the file's complete local symbol table.
"""

from __future__ import annotations

import re
from typing import Any

from ..types import EvidenceSignal, GraphEdge, GraphNode
from ._ts_nodes import (
    _ts_callee,
    _ts_component_meta,
    _ts_decorator_name,
    _ts_emit_type_edges,
    _ts_enclosing_class_uid,
    _ts_enclosing_scope,
    _ts_line,
    _ts_name,
    _ts_resolve_type,
)
from ._ts_uids import (
    _TS_KEYWORDS,
    EXTRACTOR_ID_TS,
    _ts_method_uid,
    class_uid,
    function_uid,
    interface_uid,
)
from .md_links import ExtractionResult


def _walk_ts_symbols(
    root: Any,
    *,
    path: str,
    module_uid_: str,
    file_uid_: str,
    lang: str,
    imported_names: dict[str, str],
    local_names: dict[str, str],
    result: ExtractionResult,
) -> None:
    """AST-accurate symbol/edge extraction from a tree-sitter TS/TSX tree."""
    from ..tree_sitter_overlay import iter_nodes

    # GE: per-class method map so `this.method()` resolves to THIS class's
    # method instead of an unresolved stub (matters for class-heavy TS:
    # NestJS / Angular). Populated in the class-body method loop below.
    methods_by_class: dict[str, dict[str, str]] = {}
    # Deferred type-annotation edges — resolved after Pass A (see below).
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
        name = _ts_name(cls)
        if not name:
            continue
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

    # ---- Pass B: calls / constructs sourced at the enclosing scope ----
    for call in iter_nodes(root, {"call_expression", "new_expression"}):
        fn_field = call.child_by_field_name("function") or call.child_by_field_name("constructor")
        if fn_field is None:
            fn_field = call.children[0] if call.children else None
        if fn_field is None:
            continue
        target, head = _ts_callee(fn_field)
        if not target or not re.match(r"^[\w$.]+$", target) or head in _TS_KEYWORDS:
            continue
        is_new = call.type == "new_expression"
        is_ctor = is_new or (target.split(".")[-1][:1].isupper())
        is_await = call.parent is not None and call.parent.type == "await_expression"
        src = _ts_enclosing_scope(call, path) or module_uid_
        if head == "this" and "." in target:
            # GE: this.method() → enclosing class's method (else unresolved).
            encl_cls = _ts_enclosing_class_uid(call, path)
            mname = target.split(".", 1)[1].split(".")[0]
            m_uid = methods_by_class.get(encl_cls or "", {}).get(mname)
            if m_uid:
                resolved, conf, sig = m_uid, 0.9, EvidenceSignal("this_method", 0.9)
            else:
                resolved, conf, sig = (
                    f"code:external:unresolved:{target}",
                    0.3,
                    EvidenceSignal("unresolved_call", 0.3),
                )
        elif target in local_names:
            resolved, conf, sig = local_names[target], 0.9, EvidenceSignal("same_scope", 0.9)
        elif head in local_names and "." not in target:
            resolved, conf, sig = local_names[head], 0.9, EvidenceSignal("same_scope", 0.9)
        elif head in imported_names:
            specifier = imported_names[head]
            tail = ".".join(target.split(".")[1:]) or head
            resolved, conf = f"code:external:{specifier}:{tail}", 0.9
            sig = EvidenceSignal("explicit_import", 0.9, note=specifier)
        else:
            resolved, conf, sig = (
                f"code:external:unresolved:{target}",
                0.3,
                EvidenceSignal("unresolved_call", 0.3),
            )
        edge_type = "awaits" if is_await else ("constructs" if is_ctor else "calls")
        result.edges.append(
            GraphEdge(
                source_uid=src,
                target_uid=resolved,
                edge_type=edge_type,
                extractor=EXTRACTOR_ID_TS,
                confidence=conf,
                source_span=f"{path}:{_ts_line(call)}",
                evidence=(sig,),
            )
        )

    # ---- Pass C: JSX component usage (tsx) ----
    if lang == "tsx":
        for el in iter_nodes(root, {"jsx_opening_element", "jsx_self_closing_element"}):
            nm = el.child_by_field_name("name")
            comp = nm.text.decode("utf-8", "replace") if nm is not None else ""
            if not comp or not comp[:1].isupper():
                continue  # lowercase = host element (div / View) — skip
            head = comp.split(".")[0]
            if comp in local_names:
                resolved, conf = local_names[comp], 0.8
            elif head in imported_names:
                resolved, conf = f"code:external:{imported_names[head]}:{comp}", 0.7
            else:
                resolved, conf = f"code:external:unresolved:{comp}", 0.3
            result.edges.append(
                GraphEdge(
                    source_uid=module_uid_,
                    target_uid=resolved,
                    edge_type="constructs",
                    extractor=EXTRACTOR_ID_TS,
                    confidence=conf,
                    source_span=f"{path}:{_ts_line(el)}",
                    evidence=(EvidenceSignal("jsx_component", conf),),
                )
            )
