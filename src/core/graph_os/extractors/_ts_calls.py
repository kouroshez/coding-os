"""Call and JSX-usage pass over a parsed TypeScript / TSX tree.

Every edge is sourced at its enclosing function/method — the scope resolution
regex cannot do — falling back to the module node at top level.
"""

from __future__ import annotations

import re
from typing import Any

from ..types import EvidenceSignal, GraphEdge
from ._ts_nodes import (
    _ts_callee,
    _ts_enclosing_class_uid,
    _ts_enclosing_scope,
    _ts_line,
)
from ._ts_uids import _TS_KEYWORDS, EXTRACTOR_ID_TS
from .md_links import ExtractionResult


def _walk_ts_calls(
    root: Any,
    *,
    path: str,
    module_uid_: str,
    lang: str,
    imported_names: dict[str, str],
    local_names: dict[str, str],
    methods_by_class: dict[str, dict[str, str]],
    result: ExtractionResult,
) -> None:
    """Emit calls / awaits / constructs edges, plus JSX component usage in tsx."""
    from ..tree_sitter_overlay import iter_nodes

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
