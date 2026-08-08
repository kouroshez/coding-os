"""Read/query tools: query, context, trace, similar, search, references, path.

Private module of graph_os.tools.graph — import via the graph module,
never directly (the kernel imports this file at its bottom).
"""

from __future__ import annotations

import difflib
import hashlib
from collections import deque
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ..backend import BackendUnavailable, GraphBackend
from ..types import GraphEdge, GraphNode
from . import graph as _kernel
from .graph import (
    NodeSummary,
    _contains_ancestors,
    _count_edges_for,
    _edge_to_dict,
    _fail,
    _fail_uid_not_found,
    _file_disk_hash,
    _file_freshness,
    _fts5_safe_query,
    _lexical_search,
    _looks_prefixed,
    _normalize_kinds,
    _ok,
    _resolve_uid,
    _validate_confidence,
    _validate_positive_int,
    _walk_bfs,
    _write_consult_marker,
    logger,
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


# W7.8 / R4-12: in-repo modules that act as stub-hubs because every
# Python file imports from them. Treat them like ``code:external:*``
# in path-BFS to prevent meaningless bridges.
_PATH_STUB_HUB_MODULES: frozenset[str] = frozenset(
    {
        "__future__",
        "__init__",
        "typing",
        "typing_extensions",
        "annotations",
        "builtins",
    }
)


def _is_stub_hub_uid(uid: str) -> bool:
    """True when uid is a stub-hub (external stub or in-repo module hub)."""
    if uid.startswith("code:external:"):
        return True
    if uid.startswith("code:module:"):
        module = uid.split(":", 2)[-1]
        last = module.rsplit(".", 1)[-1]
        return last in _PATH_STUB_HUB_MODULES or module in _PATH_STUB_HUB_MODULES
    return False


# R4-02: per-node-kind default edge types for cos_graph_references.
# A class is referenced by `constructs` (instantiation) — different
# vocabulary than how a function is referenced (`calls`). Pick the
# edge-types relevant to the node's kind so the default answer for
# "who references X?" is meaningful for every kind, not just functions.
_REFERENCE_KINDS_BY_NODE_KIND: dict[str, tuple[str, ...]] = {
    "class": (
        "constructs",
        "has_param_type",
        "returns_type",
        "field_of_type",
        "inherits_from",
        "is_decorated_by",
        "imports",
        "references_doc",
    ),
    "interface": (
        "implements",
        "has_param_type",
        "returns_type",
        "field_of_type",
        "inherits_from",
        "imports",
    ),
    "function": (
        "calls",
        "accesses_field",
        "imports",
        "is_decorated_by",
        "references_doc",
    ),
    "method": (
        "calls",
        "accesses_field",
        "imports",
        "is_decorated_by",
        "references_doc",
    ),
    "variable": (
        "accesses_field",
        "has_param_type",
        "references_doc",
    ),
    "module": (
        "imports",
        "calls",
        "references_doc",
    ),
    "file": (
        "imports",
        "links_to",
        "references_doc",
        "contains",
    ),
    "doc_file": (
        "links_to",
        "cites_heading",
        "references_doc",
        "read_next",
    ),
    "doc_heading": (
        "links_to",
        "cites_heading",
        "references_doc",
    ),
    "folder": (
        "contains",
        "links_to",
        "references_doc",
    ),
    "mcp_tool": (
        "calls",
        "dispatches",
        "references_doc",
    ),
    "hook": (
        "handles_tool",
        "handles_event",
        "declares",
        "references_doc",
    ),
}


def _default_reference_kinds_for(node_kind: str | None) -> tuple[str, ...]:
    """Pick default inbound edge-types based on node kind (R4-02)."""
    if not node_kind:
        return ("calls", "accesses_field", "imports", "references_doc")
    return _REFERENCE_KINDS_BY_NODE_KIND.get(
        node_kind,
        ("calls", "accesses_field", "imports", "references_doc"),
    )


# ---------------------------------------------------------------------------
# The tools
# ---------------------------------------------------------------------------


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


def cos_graph_trace(
    entry_uid: str,
    *,
    terminals: Sequence[str] = ("return", "exception"),
    max_steps: int = 50,
    include_external: bool = False,
    backend: str | None = None,
) -> dict[str, Any]:
    """Forward execution walk from an entry point.

    F9 / Audit #7: `include_external=False` (default) keeps unresolved
    builtins / stdlib stubs (`code:external:*`) out of `steps`. They
    are collected in `external_targets` instead so the walk surface
    stays project-internal but the call-site relationship is still
    visible.
    """
    # W7.1 / R4-07: max_steps=0 returned empty steps + walk_truncated=true
    # (never walked). Reject as validation error.
    err = _validate_positive_int(max_steps, "max_steps")
    if err:
        return err
    try:
        be = _kernel._backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)
    root, tried_entry_uids, resolved_from = _resolve_uid(be, entry_uid)
    start_source = "explicit"
    if root is None:
        # fall back to the highest-scoring entry point whose
        # label / file matches the supplied identifier.  Lets agents
        # call cos_graph_trace("login") without first running a
        # separate query to resolve the uid. The entry_points module
        # is part of an in-flight TASK; tolerate its absence so the
        # tool still returns a useful not_found instead of crashing.
        try:
            from .. import entry_points as ep_mod  # type: ignore[attr-defined]

            ep = ep_mod.best_start_for_query(be, entry_uid)
            if ep is not None:
                root = be.get_node(ep.uid)
                start_source = "entry-point-heuristic"
        except ImportError as exc:
            logger.debug("entry_points fallback unavailable: %s", exc)
    if root is None:
        return _fail_uid_not_found(entry_uid, tried_entry_uids, label="entry_uid")

    steps: list[dict[str, Any]] = []
    branches: list[dict[str, Any]] = []
    external_targets: list[str] = []
    seen: set[str] = set()
    stack: list[str] = [root.uid]
    while stack and len(steps) < max_steps:
        uid = stack.pop()
        if uid in seen:
            continue
        seen.add(uid)
        if not include_external and uid.startswith("code:external:"):
            external_targets.append(uid)
            continue
        node = be.get_node(uid)
        if node is None:
            continue
        steps.append(NodeSummary.from_node(node).to_dict())
        # B3: follow a wider set of outgoing control-flow edges so traces
        # cover API routes, MCP tool dispatch, event handlers, and async
        # awaits — not just direct calls/constructs.
        edges = be.list_edges(
            source_uid=uid,
            edge_types=(
                "calls",
                "constructs",
                "handles_route",
                "handles_tool",
                "handles_event",
                "dispatches",
                "awaits",
            ),
            limit=20,
        )
        if len(edges) > 1:
            # G24: strip externals from fan_out — they already live in
            # `external_targets`, so duplicating them in branches inflates
            # the envelope without new information.
            fan_out_uids = [e.target_uid for e in edges]
            if not include_external:
                fan_out_uids = [u for u in fan_out_uids if not u.startswith("code:external:")]
            branches.append(
                {
                    "from": uid,
                    "fan_out": fan_out_uids,
                }
            )
        for edge in edges:
            if edge.target_uid not in seen:
                stack.append(edge.target_uid)
    # Walk stopped either because the stack drained (complete) or
    # because the step cap fired (incomplete — caller should re-run
    # with a higher max_steps or split the trace at a branch).
    walk_truncated = len(steps) >= max_steps and bool(stack)
    return _ok(
        {
            "entry": NodeSummary.from_node(root).to_dict(),
            "steps": steps,
            "branches": branches,
            "external_targets": external_targets,
            "terminals": list(terminals),
            "start_source": start_source,
        },
        meta={
            "backend": be.backend_id,
            "step_count": len(steps),
            "external_count": len(external_targets),
            "start_source": start_source,
            "max_steps": max_steps,
            "walk_truncated": walk_truncated,
            "resolved_from": resolved_from,
        },
    )


def _similar_from_persisted(
    be: Any,
    root: GraphNode,
    *,
    top_k: int,
    confidence_min: float,
    resolved_from: str,
) -> dict[str, Any] | None:
    """Rank similar nodes from persisted graph_node embeddings (one encode,
    full pool). Returns the _ok envelope when persisted vectors are usable,
    else None so the caller falls back to the on-the-fly difflib path.
    """
    conn = getattr(be, "_conn", None)
    if conn is None:
        return None
    try:
        from thinking_os.embeddings import (
            embed_text,
            is_available,
            persisted_similarity_floor,
            search_similar,
        )
    except ImportError:
        return None
    if not is_available():
        return None
    ref_text = f"{root.label or ''} {root.signature or ''} {root.doc_blob or ''}".strip()
    if not ref_text:
        return None
    # Over-fetch beyond top_k to absorb the root self-hit + any identifier /
    # external rows, then trim.
    overfetch = max(top_k * 4, top_k + 20)
    # ANN fast path: vec0 kNN is sublinear, so this stays fast as the graph
    # grows orders of magnitude. Returns None when the extension is absent →
    # fall through to the brute-force streaming scan (always correct, O(N)).
    hits: list[dict[str, Any]] | None = None
    try:
        from graph_os import vec_index

        ref_blob = embed_text(ref_text)
        ann = vec_index.knn(conn, ref_blob, overfetch) if ref_blob else None
        if ann is not None:
            hits = [{"source_id": sid, "score": cos} for sid, cos in ann]
    except Exception as exc:
        logger.debug("vec ann path skipped (%s); falling back to brute force", exc)
    if hits is None:
        try:
            hits = search_similar(
                conn, ref_text, source_tables=["graph_nodes"], limit=overfetch, threshold=0.0
            )
        except Exception as exc:  # fail-open → caller falls back to difflib
            logger.debug("similar persisted path skipped: %s", exc)
            return None
    if not hits:
        return None
    ids = [h["source_id"] for h in hits]
    placeholders = ",".join("?" * len(ids))
    id_to_uid = {
        row[0]: row[1]
        for row in conn.execute(
            f"SELECT id, uid FROM graph_nodes WHERE id IN ({placeholders})", ids
        ).fetchall()
    }
    score_by_id = {h["source_id"]: h["score"] for h in hits}
    wanted = [id_to_uid[i] for i in ids if i in id_to_uid and id_to_uid[i] != root.uid]
    nodes_by_uid = be.get_nodes_bulk(wanted)
    # Cap the floor at the model-calibrated value (MiniLM ~0.25, BGE-M3 ~0.6)
    # so a legacy confidence_min default can't suppress the persisted path;
    # raw cosine and the legacy blended score live on different scales (P6).
    effective_floor = min(confidence_min, persisted_similarity_floor())
    scored: list[tuple[float, GraphNode]] = []
    for i in ids:  # ids are already score-descending from search_similar
        uid = id_to_uid.get(i)
        if uid is None or uid == root.uid:
            continue
        node = nodes_by_uid.get(uid)
        if node is None or node.kind == "identifier" or uid.startswith("code:external:"):
            continue
        sim = score_by_id.get(i, 0.0)
        if sim >= effective_floor:
            scored.append((sim, node))
    if not scored:
        return None
    total = len(scored)
    top_k_eff = max(1, top_k)
    results = [
        {**NodeSummary.from_node(n).to_dict(), "similarity": round(r, 4)}
        for r, n in scored[:top_k_eff]
    ]
    return _ok(
        {
            "root": NodeSummary.from_node(root).to_dict(),
            "results": results,
            "total_count": total,
        },
        meta={
            "backend": be.backend_id,
            "scorer": "persisted-embeddings",
            "top_k": top_k_eff,
            "floor": round(effective_floor, 3),
            "result_truncated": total > top_k_eff,
            "resolved_from": resolved_from,
        },
    )


def cos_graph_similar(
    uid: str,
    *,
    top_k: int = 5,
    confidence_min: float = 0.5,
    backend: str | None = None,
) -> dict[str, Any]:
    """Semantic similarity — I.8 baseline uses string similarity between
    labels + docstrings; I.1 BGE-M3 embeddings lift the signal later.

    B13: uses ``sample_nodes(kind, limit)`` to build a candidate pool
    from actual graph nodes of the same kind, rather than edge-endpoint
    sampling. Edge-endpoint sampling biases toward high-degree nodes;
    ``sample_nodes`` gives an unbiased draw over the node table.
    """
    try:
        be = _kernel._backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)
    root, tried_uids, resolved_from = _resolve_uid(be, uid)
    if root is None:
        return _fail_uid_not_found(uid, tried_uids)

    # I.1: fast path — rank from persisted graph_node embeddings (one encode,
    # full pool, ~10ms) instead of encoding ~200 candidates on the fly
    # (~1800ms measured). Returns None when no persisted vectors exist (or
    # embeddings unavailable), falling through to the difflib baseline below.
    fast = _similar_from_persisted(
        be, root, top_k=top_k, confidence_min=confidence_min, resolved_from=resolved_from
    )
    if fast is not None:
        return fast

    # B13: use sample_nodes for a breadth candidate pool. NOTE: sample_nodes
    # draws ORDER BY id ASC LIMIT — a fixed prefix of the kind, not a uniform
    # sample. So a structural near-twin outside that window is never scored
    # (round-5 audit: count_nodes' twin count_edges, same class, was never a
    # candidate). Until the sampler is made representative (follow-up task),
    # we GUARANTEE the root's container-siblings are scored below — they are
    # the most likely near-twins, so this fixes the dominant failure mode.
    sample_size = 200  # bounded to keep latency predictable
    sampler = getattr(be, "sample_nodes", None)
    if callable(sampler):
        raw_candidates = sampler(root.kind or None, sample_size)
    else:
        # Graceful degradation for backends that have not yet implemented
        # sample_nodes (should not happen post-S2, but kept for safety).
        raw_candidates = []
        seen_fallback: set[str] = set()
        for edge in be.list_edges(limit=sample_size):
            for side in (edge.source_uid, edge.target_uid):
                if side in seen_fallback:
                    continue
                seen_fallback.add(side)
                n = be.get_node(side)
                if n is not None:
                    raw_candidates.append(n)

    # Sibling augmentation: pull every node sharing the root's container
    # (class / file / module) via the CONTAINS spine so true structural
    # twins are always in the pool regardless of the sample window. One
    # bulk fetch on the collected sibling uids — not a per-sibling get_node
    # round-trip — keeps this a single query.
    try:
        sibling_uids: list[str] = []
        for parent_edge in be.list_edges(target_uid=root.uid, edge_types=["contains"], limit=8):
            sibling_uids.extend(
                e.target_uid
                for e in be.list_edges(
                    source_uid=parent_edge.source_uid,
                    edge_types=["contains"],
                    limit=1000,
                )
            )
        if sibling_uids:
            raw_candidates.extend(be.get_nodes_bulk(sibling_uids).values())
    except Exception as exc:  # fail-open: augmentation is best-effort
        logger.debug("similar sibling augmentation skipped: %s", exc)

    # F3: same-label cross-file augmentation. sample_nodes draws a fixed
    # id-prefix window and the sibling sweep only covers the root's own
    # container, so structural twins in OTHER files (e.g. the 9 `extract()`
    # functions across extractor modules) were never candidates. Pull
    # same-kind nodes sharing the root's label so cross-file near-twins are
    # always scored. Cheap + deterministic (no RANDOM()).
    _sim_conn = getattr(be, "_conn", None)
    if root.label and _sim_conn is not None:
        try:
            same_label_uids = [
                r[0]
                for r in _sim_conn.execute(
                    "SELECT uid FROM graph_nodes WHERE kind = ? AND label = ? LIMIT 200",
                    (root.kind, root.label),
                ).fetchall()
            ]
            if same_label_uids:
                raw_candidates.extend(be.get_nodes_bulk(same_label_uids).values())
        except Exception as exc:  # fail-open
            logger.debug("similar same-label augmentation skipped: %s", exc)

    # G21: drop external/orphan/unresolved stubs from the candidate pool —
    # they otherwise dominate similarity for any noise-shaped input
    # (`unresolved:str` returned 120 noise neighbours). Dedup by uid since
    # the sample and the sibling sweep can overlap. Seed with `root.uid`
    # (not just the raw `uid`): the sibling sweep walks root's container and
    # always re-includes root itself, and when the input resolved fuzzily
    # (resolved_from != "direct") root.uid != uid — so excluding only the
    # raw input would let the queried node score ~1.0 against itself.
    seen_uids: set[str] = {root.uid}
    candidates: list[GraphNode] = []
    for n in raw_candidates:
        if n.uid == uid or n.uid in seen_uids:
            continue
        if n.uid.startswith("code:external:unresolved:") or n.kind == "identifier":
            continue
        seen_uids.add(n.uid)
        candidates.append(n)

    # Use BGE-M3 embeddings when the model is available;
    # fall back to lexical SequenceMatcher otherwise. Both signals get
    # combined linearly so partially-loaded environments still rank.
    scorer_name = "difflib-baseline"
    embed_scores: dict[str, float] = {}
    try:
        from thinking_os.embeddings import (  # type: ignore
            cosine_similarity,
            embed_text,
            is_available,
        )

        if is_available():
            ref_text = (f"{root.label or ''} {root.signature or ''} {root.doc_blob or ''}").strip()
            ref_vec = embed_text(ref_text)
            if ref_vec:
                cand_texts = [
                    f"{n.label or ''} {n.signature or ''} {n.doc_blob or ''}".strip()
                    for n in candidates
                ]
                # batch encode candidate side, then cosine in one shot
                cand_vecs: list[bytes | None] = [embed_text(t) for t in cand_texts]
                valid = [v for v in cand_vecs if v]
                if valid:
                    sims = cosine_similarity(ref_vec, valid)
                    valid_iter = iter(sims)
                    for n, vec in zip(candidates, cand_vecs, strict=False):
                        if vec is not None:
                            embed_scores[n.uid] = float(next(valid_iter))
                    scorer_name = "bge-m3+difflib-blend"
    except ImportError as exc:
        logger.debug("embeddings module unavailable: %s", exc)
    except Exception as exc:
        logger.debug("embedding similarity skipped: %s", exc)

    scored = []
    reference = f"{root.label or ''} {root.signature or ''} {root.doc_blob or ''}"
    for node in candidates:
        other = f"{node.label or ''} {node.signature or ''} {node.doc_blob or ''}"
        lex = difflib.SequenceMatcher(None, reference, other).ratio()
        emb = embed_scores.get(node.uid)
        # Linear blend: 70% embedding, 30% lexical when embedding ran;
        # 100% lexical otherwise. Keeps results deterministic and lets
        # cold-start environments still answer.
        ratio = (0.7 * emb + 0.3 * lex) if emb is not None else lex
        if ratio >= confidence_min:
            scored.append((ratio, node))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    top_k_eff = max(1, top_k)
    total = len(scored)
    results = [
        {**NodeSummary.from_node(n).to_dict(), "similarity": round(r, 4)}
        for r, n in scored[:top_k_eff]
    ]
    return _ok(
        {
            "root": NodeSummary.from_node(root).to_dict(),
            "results": results,
            "total_count": total,
        },
        meta={
            "backend": be.backend_id,
            "scorer": scorer_name,
            "top_k": top_k_eff,
            "result_truncated": total > top_k_eff,
            "resolved_from": resolved_from,
        },
    )


def cos_graph_search(
    query: str,
    *,
    top_k: int = 10,
    backend: str | None = None,
) -> dict[str, Any]:
    """Hybrid semantic + lexical search over indexed code symbols by free text.

    Blends three signals: semantic cosine (ANN vec0 → cosine, brute-force
    fallback), FTS5 lexical presence, and graph in-degree (centrality). Answers
    "where is the code that does X?" without knowing a symbol name.
    """
    if not query or not query.strip():
        return _fail("validation", "query must be non-empty")
    try:
        be = _kernel._backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)
    conn = getattr(be, "_conn", None)
    if conn is None:
        return _fail("unavailable", "backend has no SQLite connection", retryable=True)

    top_k_eff = max(1, min(int(top_k), 50))
    pool = top_k_eff * 5

    # --- semantic signal (ANN → brute fallback) ---
    sem_by_id: dict[int, float] = {}
    try:
        from thinking_os.embeddings import embed_text, is_available, search_similar

        if is_available():
            blob = embed_text(query)
            if blob:
                from graph_os import vec_index

                ann = vec_index.knn(conn, blob, pool)
                if ann is None:
                    hits = search_similar(
                        conn, query, source_tables=["graph_nodes"], limit=pool, threshold=0.0
                    )
                    ann = [(h["source_id"], h["score"]) for h in hits]
                sem_by_id = {int(sid): float(cos) for sid, cos in ann}
    except Exception as exc:
        logger.debug("graph_search semantic signal skipped: %s", exc)

    # --- lexical signal (FTS5 presence over graph_nodes_fts) ---
    lex_ids: set[int] = set()
    fts_q = _fts5_safe_query(query)
    if fts_q:
        try:
            lex_ids = {
                int(r[0])
                for r in conn.execute(
                    "SELECT rowid FROM graph_nodes_fts WHERE graph_nodes_fts MATCH ? LIMIT ?",
                    (fts_q, pool),
                ).fetchall()
            }
        except Exception as exc:
            logger.debug("graph_search lexical signal skipped: %s", exc)

    cand_ids = set(sem_by_id) | lex_ids
    if not cand_ids:
        return _ok(
            {"query": query, "results": [], "total_count": 0},
            meta={"backend": be.backend_id, "scorer": "hybrid", "top_k": top_k_eff},
        )

    # --- centrality signal (in-degree over the candidate set, normalised) ---
    deg_by_id: dict[int, int] = {}
    id_list = list(cand_ids)
    ph = ",".join("?" * len(id_list))
    try:
        for r in conn.execute(
            f"SELECT target_id, COUNT(*) FROM graph_edges_v12 "
            f"WHERE target_id IN ({ph}) GROUP BY target_id",
            id_list,
        ).fetchall():
            deg_by_id[int(r[0])] = int(r[1])
    except Exception as exc:
        logger.debug("graph_search centrality signal skipped: %s", exc)
    max_deg = max(deg_by_id.values(), default=0)

    # --- blend + resolve to nodes ---
    id_to_uid = {
        int(row[0]): row[1]
        for row in conn.execute(
            f"SELECT id, uid FROM graph_nodes WHERE id IN ({ph})", id_list
        ).fetchall()
    }
    nodes_by_uid = be.get_nodes_bulk(list(id_to_uid.values()))
    scored: list[tuple[float, GraphNode]] = []
    for gid in cand_ids:
        uid = id_to_uid.get(gid)
        node = nodes_by_uid.get(uid) if uid else None
        if node is None or node.kind == "identifier" or uid.startswith("code:external:"):
            continue
        sem = sem_by_id.get(gid, 0.0)
        lex = 1.0 if gid in lex_ids else 0.0
        deg = (deg_by_id.get(gid, 0) / max_deg) if max_deg else 0.0
        score = 0.7 * sem + 0.2 * lex + 0.1 * deg
        scored.append((score, node))
    scored.sort(key=lambda p: p[0], reverse=True)
    total = len(scored)
    results = [
        {**NodeSummary.from_node(n).to_dict(), "score": round(s, 4)} for s, n in scored[:top_k_eff]
    ]
    return _ok(
        {"query": query, "results": results, "total_count": total},
        meta={
            "backend": be.backend_id,
            "scorer": "hybrid",
            "top_k": top_k_eff,
            "result_truncated": total > top_k_eff,
        },
    )


def cos_graph_references(
    uid: str,
    *,
    kinds: Sequence[str] | str | None = None,
    limit: int = 100,
    backend: str | None = None,
) -> dict[str, Any]:
    """Inbound edges to `uid` — "who references this?".

    Coverage contract (so silent truncation can't bite the agent):
      - ``count`` is the rows in *this* response (≤ limit).
      - ``total_count`` is the TRUE inbound-edge count across the kinds
        filter. If ``count < total_count`` the response is incomplete —
        the agent must either widen ``limit`` or narrow ``kinds``.
      - ``meta.result_truncated`` mirrors the same condition for fast
        inspection. (Distinct from the envelope-level ``meta.truncated``
        which signals *token-budget* truncation; result_truncated signals
        the caller-budget hit.)
    """
    # G22: validate + clamp limit
    if limit is not None and limit <= 0:
        return _fail("validation", "limit must be > 0")
    _LIMIT_MAX = 10_000
    limit_clamped = False
    if limit and limit > _LIMIT_MAX:
        limit = _LIMIT_MAX
        limit_clamped = True
    # G2 + G3: normalize kinds (caller-supplied wins; per-kind default
    # below kicks in only when caller passes empty).
    parsed_kinds = _normalize_kinds(kinds)

    try:
        be = _kernel._backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)
    node, tried_uids, resolved_from = _resolve_uid(be, uid)
    if node is None:
        return _fail_uid_not_found(uid, tried_uids)

    # R4-02: per-kind default — class nodes are accessed via `constructs`
    # (test instantiations) which is NOT in the function-default. Pick a
    # sensible default per node.kind so callers don't get 0 callers on a
    # class that has 30+ test constructs.
    defaults_were_picked = False
    if not parsed_kinds:
        parsed_kinds = _default_reference_kinds_for(node.kind)
        defaults_were_picked = True

    canonical_uid = node.uid
    edges = be.list_edges(target_uid=canonical_uid, edge_types=parsed_kinds, limit=limit)

    # True total — separate count query so the caller knows if `edges`
    # is a complete picture or a slice. Uses the same kinds filter
    # because the backend's list_edges does the same filtering.
    total = _count_edges_for(be, target_uid=canonical_uid, edge_types=parsed_kinds)
    truncated = total > len(edges)

    references_meta: dict[str, Any] = {
        "backend": be.backend_id,
        "kinds": list(parsed_kinds),
        "limit": limit,
        "limit_clamped": limit_clamped,
        "result_truncated": truncated,
        "resolved_from": resolved_from,
        "default_kinds_picked": defaults_were_picked,
        "node_kind": node.kind,
    }
    fresh = _file_freshness(be, node.file_path)
    if fresh is not None:
        references_meta["stale"] = fresh["stale"]
        references_meta["freshness"] = fresh
    return _ok(
        {
            "node": NodeSummary.from_node(node).to_dict(),
            "references": [_edge_to_dict(e) for e in edges],
            "count": len(edges),
            "total_count": total,
        },
        meta=references_meta,
    )


def cos_graph_path(
    source_uid: str,
    target_uid: str,
    *,
    max_hops: int = 5,
    allow_external_intermediates: bool = False,
    backend: str | None = None,
) -> dict[str, Any]:
    """Shortest path between two nodes (any direction).

    B4: each hop pulls up to 1000 edges from the backend (up from 200).
    When either side's edge list hits that cap the result is flagged
    ``meta.truncated=True`` so callers know the search may have missed a
    shorter path that lives beyond the first 1000 neighbours.

    W6.4 (T1): `code:external:*` stubs are excluded from intermediate
    hops by default because `unresolved:str` has thousands of in-edges
    and produces meaningless bridges between unrelated nodes. Pass
    ``allow_external_intermediates=True`` to opt back in.
    """
    try:
        be = _kernel._backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)
    src_node, tried_src, src_resolved_from = _resolve_uid(be, source_uid)
    if src_node is None:
        return _fail_uid_not_found(source_uid, tried_src, label="source_uid")
    tgt_node, tried_tgt, tgt_resolved_from = _resolve_uid(be, target_uid)
    if tgt_node is None:
        return _fail_uid_not_found(target_uid, tried_tgt, label="target_uid")
    source_uid = src_node.uid
    target_uid = tgt_node.uid
    # G11/G23/P5: separate the two distinct truncation concepts:
    #   * `walk_truncated` — search ran out of budget BEFORE reaching target
    #     (the previous "truncated" semantics blurred this with fanout-cap).
    #   * `frontier_saturated` — per-node fanout hit the cap (search may
    #     still have succeeded, but a wider neighbour list could yield a
    #     shorter path). Was the original `walk_truncated` semantics —
    #     renamed to stop the false-positive panic on 3-hop paths.
    # P5: hop edge cap reduced 1000 → 200 to stay sub-100ms at 1M-node.
    _PATH_HOP_LIMIT = 200
    frontier_saturated = False
    # W6.4 (T2): parents stores (prev_uid, edge, traversal_direction).
    parents: dict[str, tuple[str, GraphEdge, str] | None] = {source_uid: None}
    queue: deque[tuple[str, int]] = deque([(source_uid, 0)])
    found = source_uid == target_uid
    while queue and not found:
        uid, depth = queue.popleft()
        if uid == target_uid:
            found = True
            break
        if depth >= max_hops:
            continue
        out_edges = be.list_edges(source_uid=uid, limit=_PATH_HOP_LIMIT)
        if len(out_edges) >= _PATH_HOP_LIMIT:
            frontier_saturated = True
        for edge in out_edges:
            nxt = edge.target_uid
            # W6.4 (T1) + W7.8 (R4-12): skip external stubs AND in-repo
            # stub-hub modules (__future__, typing, __init__, …) which
            # bridge unrelated nodes. Target uid always exempt.
            if not allow_external_intermediates and _is_stub_hub_uid(nxt) and nxt != target_uid:
                continue
            if nxt not in parents:
                parents[nxt] = (uid, edge, "forward")
                queue.append((nxt, depth + 1))
        in_edges = be.list_edges(target_uid=uid, limit=_PATH_HOP_LIMIT)
        if len(in_edges) >= _PATH_HOP_LIMIT:
            frontier_saturated = True
        for edge in in_edges:
            nxt = edge.source_uid
            if not allow_external_intermediates and _is_stub_hub_uid(nxt) and nxt != target_uid:
                continue
            if nxt not in parents:
                parents[nxt] = (uid, edge, "reverse")
                queue.append((nxt, depth + 1))
    walk_truncated = (target_uid not in parents) and frontier_saturated
    if target_uid not in parents:
        return _ok(
            {
                "path": None,
                "edges": [],
                "walk_truncated": walk_truncated,
                "frontier_saturated": frontier_saturated,
            },
            meta={
                "backend": be.backend_id,
                "reason": "unreachable" if not frontier_saturated else "exhausted_budget",
                "walk_truncated": walk_truncated,
                "frontier_saturated": frontier_saturated,
                "max_hops": max_hops,
                "frontier_edge_limit": _PATH_HOP_LIMIT,
                "source_resolved_from": src_resolved_from,
                "target_resolved_from": tgt_resolved_from,
            },
        )
    chain: list[tuple[GraphEdge, str]] = []
    cur = target_uid
    while parents.get(cur) is not None:
        prev, edge, traversal_dir = parents[cur]  # type: ignore[misc]
        chain.append((edge, traversal_dir))
        cur = prev
    chain.reverse()
    # G29: walk the chain step-by-step so we don't emit consecutive
    # duplicate nodes. The previous "[source] + [e.target if e.source==source
    # else e.source for e]" was anchored to the original source, which broke
    # past the first hop.
    path_nodes: list[str] = [source_uid]
    prev_uid = source_uid
    edge_dicts: list[dict[str, Any]] = []
    for e, traversal_dir in chain:
        nxt_uid = e.target_uid if e.source_uid == prev_uid else e.source_uid
        path_nodes.append(nxt_uid)
        prev_uid = nxt_uid
        # W6.4 (T2): tag each edge with how the BFS traversed it so callers
        # can tell semantic-direction edges from reverse-edge bridges.
        ed = _edge_to_dict(e)
        ed["traversal_direction"] = traversal_dir
        edge_dicts.append(ed)
    return _ok(
        {
            "path": path_nodes,
            "edges": edge_dicts,
            "hops": len(chain),
            "walk_truncated": False,
            "frontier_saturated": frontier_saturated,
        },
        meta={
            "backend": be.backend_id,
            "walk_truncated": False,
            "frontier_saturated": frontier_saturated,
            "max_hops": max_hops,
            "frontier_edge_limit": _PATH_HOP_LIMIT,
            "allow_external_intermediates": allow_external_intermediates,
            "source_resolved_from": src_resolved_from,
            "target_resolved_from": tgt_resolved_from,
        },
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
