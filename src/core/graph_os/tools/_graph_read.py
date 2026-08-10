"""Neighbourhood reads: cos_graph_query and cos_graph_context.

Private module of graph_os.tools.graph — import via the graph module,
never directly (the kernel imports this file at its bottom).
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ..backend import (
    BackendUnavailable,
    GraphBackend,
)
from ..types import GraphNode
from . import graph as _kernel
from ._graph_envelope import (
    _fail,
    _file_disk_hash,
    _ok,
    _validate_confidence,
    _validate_positive_int,
    _write_consult_marker,
    logger,
)
from ._graph_lookup import (
    _fail_uid_not_found,
    _lexical_search,
    _looks_prefixed,
    _normalize_kinds,
    _resolve_uid,
)
from ._graph_walk import (
    NodeSummary,
    _contains_ancestors,
    _edge_to_dict,
    _walk_bfs,
)


def _mark_file_consulted(
    backend_obj: GraphBackend, file_path: str | None, *, tool: str
) -> dict[str, Any] | None:
    if not file_path:
        return None
    disk = _file_disk_hash(file_path)
    file_node = backend_obj.get_node(f"code:file:{file_path}")
    indexed = file_node.content_hash if file_node else None
    key = hashlib.sha1(file_path.encode("utf-8")).hexdigest()
    _write_consult_marker(
        f"ctx-{key}",
        {"file": file_path, "content_hash": disk, "indexed_hash": indexed, "tool": tool},
    )
    if disk is None or indexed is None:
        return None
    return {"stale": disk != indexed, "disk_hash": disk, "indexed_hash": indexed}


def cos_graph_query(
    q: str,
    *,
    kinds: Sequence[str] | None = None,
    limit: int = 10,
    max_hops: int = 2,
    confidence_min: float = 0.3,
    include_spine: bool = False,
    backend: str | None = None,
) -> dict[str, Any]:
    """Hybrid search over node labels + docstrings.

    DEPENDS:      GraphBackend.
    """
    # G3: normalize kinds (handles wire-stringified list trap)
    parsed_kinds = _normalize_kinds(kinds)
    if (not q or not q.strip()) and not parsed_kinds:
        return _fail(
            "validation", "query must be a non-empty string (or provide kinds for kind-only browse)"
        )
    # G32: single-char queries produce 100-row token bombs (LIKE '%x%'
    # matches every identifier containing 'x'). Require ≥2 chars unless
    # kind-only browse.
    if q and q.strip() and len(q.strip()) < 2 and not parsed_kinds:
        return _fail("validation", "query must be ≥2 chars (or pass kinds for kind-only browse)")
    # W7.1 / R4-08/R4-26: limit + confidence_min validation
    err = _validate_positive_int(limit, "limit")
    if err:
        return err
    err = _validate_confidence(confidence_min, "confidence_min")
    if err:
        return err
    try:
        be = _kernel._backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)

    kinds_filter = parsed_kinds if parsed_kinds else None
    nodes = _lexical_search(be, q=q, kinds=kinds_filter, limit=limit, max_hops=max_hops)

    # Fallback — when lexical hybrid returns nothing AND the query
    # *looks* like a path or uid, try _resolve_uid so agents who pass
    # "adapters/claude/sdk_dispatcher.py" or "ClaudeSDKDispatcher.dispatch"
    # get a hit instead of an empty list. Cheap (one DB lookup) and
    # additive — successful searches are untouched. Kind filter still
    # applies: if the resolved node's kind isn't allowed, skip the
    # fallback so behaviour matches the no-fallback path.
    if not nodes and q and q.strip():
        candidate = q.strip()
        looks_pathlike = (
            "/" in candidate
            or "::" in candidate
            or candidate.endswith((".py", ".ts", ".tsx", ".sh", ".md", ".yaml"))
            or _looks_prefixed(candidate)
        )
        if looks_pathlike:
            resolved, _tried, _src = _resolve_uid(be, candidate)
            if resolved is not None and (kinds_filter is None or resolved.kind in kinds_filter):
                nodes = [resolved]

    results = [
        {
            **NodeSummary.from_node(n).to_dict(),
            "confidence": 1.0,
        }
        for n in nodes
    ]
    # S3: when include_spine is set, attach a ``spine`` list per result
    # — the CONTAINS-ancestor chain from repo-root down to the result.
    if include_spine:
        for result_dict, node in zip(results, nodes, strict=False):
            ancestors, _ = _contains_ancestors(be, leaf_uid=node.uid)
            result_dict["spine"] = [NodeSummary.from_node(a).to_dict() for a in ancestors]
    # B22: cap meta.query to 500 chars with ellipsis suffix so the
    # envelope stays bounded regardless of how long the query string is.
    _MAX_QUERY_META = 500
    query_meta = q if len(q) <= _MAX_QUERY_META else q[:_MAX_QUERY_META] + "..."

    # process grouping. Group hit uids by Louvain community
    # so the Search tab can render `LoginFlow` / `RegistrationFlow`
    # buckets.  Communities are computed lazily per backend with a
    # cheap edge-count signature; queries with no clustering signal
    # see an empty `processes` list and the UI falls back to flat.
    processes: list[dict[str, Any]] = []
    try:
        from .. import communities as comm_mod

        all_communities, _membership = comm_mod.compute_communities(be)
        relevant_uids = {n.uid for n in nodes}
        processes = comm_mod.communities_to_processes(all_communities, relevant_uids=relevant_uids)
    except Exception as exc:
        logger.debug("community grouping suppressed: %s", exc)
        processes = []

    total = len(results)
    # G25: omit `processes` from payload when empty so the envelope
    # shape doesn't carry a constant noise key. Keep `process_count`
    # in meta so callers can detect community-grouping availability.
    payload: dict[str, Any] = {
        "results": results[:limit],
        "total_count": total,
    }
    if processes:
        payload["processes"] = processes
    return _ok(
        payload,
        meta={
            "query": query_meta,
            "backend": be.backend_id,
            "include_spine": include_spine,
            "process_count": len(processes),
            "limit": limit,
            "result_truncated": total > limit,
        },
    )


def cos_graph_context(
    uid_or_name: str,
    *,
    direction: str = "both",
    depth: int = 1,
    include_content: bool = False,
    include_evidence: bool = False,
    include_spine: bool = False,
    visit_limit: int = 500,
    backend: str | None = None,
) -> dict[str, Any]:
    """Neighbourhood around a node.

    Coverage: when the BFS hits ``visit_limit`` before exhausting the
    reachable frontier the result is incomplete — ``data.meta.walk_truncated``
    surfaces that signal so callers can re-run with a higher cap or a
    smaller ``depth``. (Distinct from the envelope-level ``meta.truncated``
    which signals *token-budget* trimming applied by the response layer.)
    """
    try:
        be = _kernel._backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)

    root, tried_uids, resolved_from = _resolve_uid(be, uid_or_name)
    if root is None:
        root = _fuzzy_resolve(be, uid_or_name)
        if root is not None:
            resolved_from = "fuzzy_label"
    if root is None:
        return _fail_uid_not_found(uid_or_name, tried_uids, label="uid_or_name")

    # two response shapes by depth.
    #   depth=1 → full (UI path: ~2KB typical, ContextPanel renders nodes)
    #   depth>=2 → SUMMARY (agent path: counts + top-5 sample per edge_type,
    #              drops full `neighbours`). Graph must be CHEAPER than file
    #              reads — at depth=2 on a 150-caller hub, dumping 108 full
    #              NodeSummary entries (~50KB) defeats the entire point of
    #              the graph layer. Agent gets actionable summary; if it
    #              needs more, it calls cos_graph_references(target_uid).
    # W7 / R4-21: cap depth at a sane ceiling. depth=99 used to be
    # echoed verbatim into meta while the BFS only ever did ~2 hops
    # under the SUMMARY visit_limit — a silent lie. Cap + surface
    # requested-vs-delivered so the agent knows the walk was bounded.
    _DEPTH_CEILING = 4
    requested_depth = int(depth)
    _depth = max(1, min(requested_depth, _DEPTH_CEILING))
    depth_clamped = requested_depth > _DEPTH_CEILING
    visit_limit = max(1, min(int(visit_limit), 50_000))
    if _depth >= 2 and visit_limit > 50:
        visit_limit = 50
    nodes, edges = _walk_bfs(
        be,
        root_uid=root.uid,
        direction=direction,
        max_hops=_depth,
        confidence_min=0.0,
        edge_types=None,
        visit_limit=visit_limit,
    )
    truncated = len(nodes) >= visit_limit
    nodes_by_uid = {n.uid: n for n in nodes}
    nodes_by_uid[root.uid] = root

    def _node_dict(node: GraphNode) -> dict[str, Any]:
        d = NodeSummary.from_node(node).to_dict()
        if include_content:
            snippet = _read_node_content(node)
            if snippet is not None:
                d["content"] = snippet["content"]
                d["truncated"] = snippet["truncated"]
        return d

    grouped: dict[str, list[dict[str, Any]]] = {}
    for e in edges:
        other_uid = e.target_uid if e.source_uid == root.uid else e.source_uid
        other = nodes_by_uid.get(other_uid)
        if other is None:
            continue
        if _depth == 1:
            full_entry: dict[str, Any] = {
                "uid": other.uid,
                "kind": other.kind,
                "label": other.label,
                "edge_type": e.edge_type,
                "confidence": e.confidence,
                "extractor": e.extractor,
            }
            if include_evidence and e.evidence:
                full_entry["evidence"] = [
                    {"signal_name": s.signal_name, "weight": s.weight, "note": s.note}
                    for s in e.evidence
                ]
            grouped.setdefault(e.edge_type, []).append(full_entry)
        else:
            # Summary mode — uid+label only. Caller drills via references.
            summary_entry = {
                "uid": other.uid,
                "label": other.label,
                "edge_type": e.edge_type,
            }
            grouped.setdefault(e.edge_type, []).append(summary_entry)

    extra_meta: dict[str, Any] = {}
    if _depth == 1:
        payload: dict[str, Any] = {
            "node": _node_dict(root),
            "neighbours": [_node_dict(n) for n in nodes if n.uid != root.uid],
            "edges_by_type": grouped,
            "edge_count": len(edges),
        }
    else:
        # Summary shape — counts + top-5 sample per edge_type. No raw
        # `neighbours` (redundant + huge on high fan-in). `edge_counts`
        # tells the agent the shape; `top_edges_by_type` shows
        # representative items to drill into via cos_graph_references.
        edge_counts = {k: len(v) for k, v in grouped.items()}
        top_edges = {k: v[:5] for k, v in grouped.items()}
        payload = {
            "node": _node_dict(root),
            "edge_counts": edge_counts,
            "top_edges_by_type": top_edges,
            "edge_count": len(edges),
            "summary_mode": True,
        }
        # drill_hint lives in meta (diagnostic), not payload — saves
        # 92 bytes per call × every depth>=2 invocation at scale.
        extra_meta["drill_hint"] = (
            "depth>=2 returns summary only. For full edge list call "
            "cos_graph_references(uid, kinds=[edge_type], limit=...)."
        )
    if include_spine:
        # S3: surface the CONTAINS-ancestor chain (repo-root → … → leaf)
        # so the SPA can render breadcrumbs alongside the context view.
        ancestors, spine_edges = _contains_ancestors(be, leaf_uid=root.uid)
        payload["spine"] = [NodeSummary.from_node(a).to_dict() for a in ancestors]
        payload["spine_edges"] = [_edge_to_dict(e) for e in spine_edges]
    freshness = _mark_file_consulted(be, root.file_path, tool="cos_graph_context")
    if freshness is not None:
        extra_meta["freshness"] = freshness
        extra_meta["stale"] = freshness["stale"]
    return _ok(
        payload,
        meta={
            "backend": be.backend_id,
            "depth": _depth,
            "requested_depth": requested_depth,
            "delivered_depth": _depth,
            "depth_clamped": depth_clamped,
            "direction": direction,
            "include_spine": include_spine,
            "visit_limit": visit_limit,
            "walk_truncated": truncated,
            "resolved_from": resolved_from,
            **extra_meta,
        },
    )


def _read_node_content(node: GraphNode, *, cap: int = 2000) -> dict[str, Any] | None:
    """B21: read source snippet for a node from its file_path + line range."""
    if not node.file_path:
        return None
    try:
        src = Path(node.file_path)
        if not src.is_file():
            return None
        lines = src.read_text(encoding="utf-8", errors="replace").splitlines()
        start = max(0, (node.start_line or 1) - 1)  # 1-indexed → 0-indexed
        end = node.end_line or node.start_line or len(lines)
        snippet = "\n".join(lines[start:end])
        truncated = len(snippet) > cap
        return {"content": snippet[:cap], "truncated": truncated}
    except Exception as exc:
        logger.debug("_read_node_content skipped for %s: %s", node.uid, exc)
        return None


def _fuzzy_resolve(backend: GraphBackend, needle: str) -> GraphNode | None:
    """Fallback for `cos_graph_context("UserService")` — try a label match.

    Scans edges to collect nodes, then difflib-scores by label. Bounded
    to 200 candidates so latency is predictable.
    """
    lower = needle.lower()
    seen: dict[str, GraphNode] = {}
    for edge in backend.list_edges(limit=500):
        for side in (edge.source_uid, edge.target_uid):
            if side in seen:
                continue
            node = backend.get_node(side)
            if node is None:
                continue
            if needle in (node.uid or "") or lower in (node.label or "").lower():
                return node
            seen[side] = node
    return None
