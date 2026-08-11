"""Blast-radius and change-detection tools: impact and detect_changes."""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from typing import Any

from ..backend import BackendUnavailable, GraphBackend
from ..types import GraphEdge, GraphNode
from . import graph as _kernel
from .graph import (
    _BEHAVIOURAL_EDGE_TYPES,
    NodeSummary,
    _edge_to_dict,
    _fail,
    _fail_uid_not_found,
    _file_freshness,
    _normalize_kinds,
    _ok,
    _resolve_uid,
    _validate_confidence,
    _validate_positive_int,
    _walk_bfs,
)


def _file_contained_symbols(backend: GraphBackend, file_uid: str, *, limit: int = 500) -> list[str]:
    # W6.3 (F6/B15/N1): when caller hands us a `code:file:*` uid the
    # interesting blast radius lives on the SYMBOLS the file contains
    # (class/function/method), not on the file node itself. Return the
    # contains-children that have behavioural inbound surface area —
    # so impact + detect_changes can roll the file-level answer up from
    # the contained symbols.
    try:
        edges = backend.list_edges(source_uid=file_uid, edge_types=("contains",), limit=limit)
    except (BackendUnavailable, sqlite3.Error):
        # Read-fallback only — caller already has a valid root node;
        # missing contained-symbol expansion degrades to file-only walk.
        # Narrowed from bare-except so KeyboardInterrupt/SystemExit propagate.
        return []
    out: list[str] = []
    for e in edges:
        tgt = e.target_uid
        # Only symbol uids carry behavioural inbound edges.
        if tgt.startswith(("code:class:", "code:function:", "code:method:")):
            out.append(tgt)
    return out


def cos_graph_impact(
    uid: str,
    *,
    direction: str = "downstream",
    depth: int = 3,
    confidence_min: float = 0.3,
    visit_limit: int = 500,
    backend: str | None = None,
) -> dict[str, Any]:
    """Blast-radius: which nodes depend on (or are depended on by) `uid`.

    Direction semantics (B12):
      "downstream" — nodes that DEPEND ON `uid` (inbound edges from
                     their perspective, i.e. direction="in" in BFS).
                     These are the nodes that WILL BREAK if `uid`
                     changes. Example: callers of a function.

      "upstream"   — nodes that `uid` DEPENDS ON (outbound edges from
                     `uid`'s perspective, i.e. direction="out" in BFS).
                     These are the nodes `uid` CALLS / IMPORTS. Changes
                     to upstream nodes may require `uid` to adapt.
                     Example: libraries or helpers that `uid` imports.

      "both"       — walks in both directions simultaneously.

    DEPRECATION NOTE: the string "downstream" / "upstream" naming
      matches the semantic intent (downstream = consumers, upstream =
      dependencies). The legacy mapping to BFS direction is preserved
      exactly. Do NOT pass raw BFS direction strings ("in"/"out") to
      this parameter — they are unsupported and will default to "in".
    """
    # W7.1 / R4-19/R4-20: confidence in [0,1] + depth>=1.
    err = _validate_confidence(confidence_min, "confidence_min")
    if err:
        return err
    err = _validate_positive_int(depth, "depth")
    if err:
        return err
    try:
        be = _kernel._backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)
    root, tried_uids, resolved_from = _resolve_uid(be, uid)
    if root is None:
        return _fail_uid_not_found(uid, tried_uids)

    walk_direction = {"downstream": "in", "upstream": "out", "both": "both"}.get(direction, "in")
    visit_limit = max(1, min(int(visit_limit), 50_000))

    # W6.3 (N1): file uids have ~no behavioural inbound edges of their
    # own — the blast radius lives on contained symbols. Walk each child
    # and merge the dedup'd union so callers asking about a file get a
    # meaningful answer instead of will_break=[].
    walk_roots = [root.uid]
    expanded_from_file = False
    if root.kind == "file":
        children = _file_contained_symbols(be, root.uid, limit=visit_limit)
        if children:
            # Children carry the behavioural surface area; the file uid
            # itself has only contains-edges (already walked as parents
            # of each child) and would consume visit_limit budget for
            # zero new signal. Drop it.
            walk_roots = children
            expanded_from_file = True

    seen_node_uids: set[str] = set()
    edges: list[GraphEdge] = []
    nodes: list[GraphNode] = []
    seen_edge_keys: set[tuple] = set()
    for sub_root in walk_roots:
        if len(seen_node_uids) >= visit_limit:
            break
        sub_nodes, sub_edges = _walk_bfs(
            be,
            root_uid=sub_root,
            direction=walk_direction,
            max_hops=max(1, int(depth)),
            confidence_min=confidence_min,
            edge_types=None,
            visit_limit=max(1, visit_limit - len(seen_node_uids)),
        )
        for n in sub_nodes:
            if n.uid in seen_node_uids:
                continue
            seen_node_uids.add(n.uid)
            nodes.append(n)
        for e in sub_edges:
            key = (e.source_uid, e.target_uid, e.edge_type)
            if key in seen_edge_keys:
                continue
            seen_edge_keys.add(key)
            edges.append(e)
    truncated = len(seen_node_uids) >= visit_limit
    tiers: dict[str, list[dict[str, Any]]] = {
        "will_break": [],
        "should_review": [],
        "context": [],
    }
    # F4 / Audit #5: tier classification is edge-type-aware, not pure
    # confidence. `contains` (file→class) has confidence=1.0 but is
    # structural — it never "breaks" when the target changes. Only
    # behavioural edges (calls / imports / constructs / type-usage /
    # dispatch / handler-binding) belong in `will_break`. Single SSOT
    # in `_BEHAVIOURAL_EDGE_TYPES` (module-level) so rename_plan +
    # impact stay in lockstep.
    for edge in edges:
        if edge.edge_type in _BEHAVIOURAL_EDGE_TYPES:
            if edge.confidence >= 0.7:
                bucket = "will_break"
            elif edge.confidence >= 0.4:
                bucket = "should_review"
            else:
                bucket = "context"
        else:
            # Structural / metadata edge (contains, tested_by, …) —
            # never a break risk; surface as context so the consumer
            # still sees the relationship.
            bucket = "context"
        tiers[bucket].append(_edge_to_dict(edge))

    impact_meta: dict[str, Any] = {
        "backend": be.backend_id,
        "depth": depth,
        "confidence_min": confidence_min,
        "visit_limit": visit_limit,
        "walk_truncated": truncated,
        "semantic_scope": "transitive_depth_" + str(depth),
        "expanded_from_file": expanded_from_file,
        "resolved_from": resolved_from,
    }
    fresh = _file_freshness(be, root.file_path)
    if fresh is not None:
        impact_meta["stale"] = fresh["stale"]
        impact_meta["freshness"] = fresh
    return _ok(
        {
            "root": NodeSummary.from_node(root).to_dict(),
            "direction": direction,
            "tiers": tiers,
            "impacted_count": max(0, len(nodes) - 1),
        },
        meta=impact_meta,
    )


def cos_graph_detect_changes(
    *,
    scope: str = "working",
    files: Sequence[str] | None = None,
    analyze_downstream: bool = True,
    backend: str | None = None,
) -> dict[str, Any]:
    """Pre-commit self-review: map changed files to affected graph nodes."""
    # G3: normalize files (FastMCP wire trap)
    parsed_files = _normalize_kinds(files)
    if not parsed_files:
        return _ok(
            {
                "scope": scope,
                "files": [],
                "symbols": [],
                "downstream_tasks": [],
                "risk_level": "none",
            },
            meta={"reason": "no files provided"},
        )
    try:
        be = _kernel._backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)

    affected_symbols: list[dict[str, Any]] = []
    downstream_tasks: set[str] = set()
    downstream_consumers: list[dict[str, Any]] = []
    risk = "low"
    _DC_VISIT_LIMIT = 500
    walk_truncated = False

    for file_path in parsed_files:
        file_uid = f"code:file:{file_path}"
        node = be.get_node(file_uid)
        if node is None:
            continue
        nodes_1, edges = _walk_bfs(
            be,
            root_uid=file_uid,
            direction="both",
            max_hops=1,
            confidence_min=0.0,
            edge_types=None,
            visit_limit=_DC_VISIT_LIMIT,
        )
        if len(nodes_1) >= _DC_VISIT_LIMIT:
            walk_truncated = True
        for edge in edges:
            affected_symbols.append(
                {
                    "file": file_path,
                    "source": edge.source_uid,
                    "target": edge.target_uid,
                    "edge_type": edge.edge_type,
                }
            )
            # B15: collect task uids from both the 1-hop walk and, below,
            # the deep walk (depth 3, confidence >= 0.6).
            for uid_candidate in (edge.source_uid, edge.target_uid):
                if uid_candidate.startswith("task:file:"):
                    downstream_tasks.add(uid_candidate)
        if analyze_downstream:
            # W6.3 (F6/B15): walk from each contained SYMBOL (class/function/
            # method) instead of the file uid alone. File-level walk only
            # surfaces folder-contains parents — useless for risk. Roll the
            # behavioural inbound counts UP to file-level risk.
            walk_seeds = _file_contained_symbols(be, file_uid, limit=_DC_VISIT_LIMIT)
            if not walk_seeds:
                walk_seeds = [file_uid]
            seen_uids: set[str] = set()
            deep_edges: list[GraphEdge] = []
            seen_edges: set[tuple] = set()
            for seed in walk_seeds:
                if len(seen_uids) >= _DC_VISIT_LIMIT:
                    walk_truncated = True
                    break
                nodes_deep, sub_edges = _walk_bfs(
                    be,
                    root_uid=seed,
                    direction="in",
                    max_hops=3,
                    confidence_min=0.6,
                    edge_types=None,
                    visit_limit=max(1, _DC_VISIT_LIMIT - len(seen_uids)),
                )
                for n in nodes_deep:
                    seen_uids.add(n.uid)
                for e in sub_edges:
                    k = (e.source_uid, e.target_uid, e.edge_type)
                    if k in seen_edges:
                        continue
                    seen_edges.add(k)
                    deep_edges.append(e)
            if len(seen_uids) >= _DC_VISIT_LIMIT:
                walk_truncated = True
            # B15: also collect task uids from the deep (depth-3) walk.
            for deep_edge in deep_edges:
                for uid_candidate in (deep_edge.source_uid, deep_edge.target_uid):
                    if uid_candidate.startswith("task:file:"):
                        downstream_tasks.add(uid_candidate)
            # G19: risk reflects BLAST RADIUS (callers / behavioural
            # consumers), not contains-children inside the file. A new
            # file with 30 functions but zero callers is "low", not "high".
            behavioural = [e for e in deep_edges if e.edge_type in _BEHAVIOURAL_EDGE_TYPES]
            # F4: expose the computed blast radius (inbound behavioural
            # consumers). Previously this drove `risk` then was discarded,
            # so callers saw only contains-children — never the real callers
            # the walk already found.
            for e in behavioural:
                downstream_consumers.append(
                    {
                        "file": file_path,
                        "consumer": e.source_uid,
                        "target": e.target_uid,
                        "edge_type": e.edge_type,
                        "confidence": e.confidence,
                    }
                )
            if len(behavioural) > 20:
                risk = "high"
            elif len(behavioural) > 5 and risk != "high":
                risk = "medium"

    return _ok(
        {
            "scope": scope,
            "files": list(files),
            "symbols": affected_symbols,
            "downstream_consumers": downstream_consumers,
            "downstream_tasks": sorted(downstream_tasks),
            "risk_level": risk,
        },
        meta={
            "backend": be.backend_id,
            "analyze_downstream": analyze_downstream,
            "downstream_consumer_count": len(downstream_consumers),
            "visit_limit": _DC_VISIT_LIMIT,
            "walk_truncated": walk_truncated,
        },
    )
