"""graph-os — the 11 cos_graph_* MCP tools (I.8).

PURPOSE:  Expose graph-os to agents through the MCP server. Every tool
          honours the Rule 14 envelope contract (ok / fail, @safe_tool)
          and sets `data.meta.layer="graph"` so agents can see which
          retrieval layer answered them.
INPUT:    arguments per-tool (see docstrings).
OUTPUT:   envelope dicts produced by `core/thinking_os/tools/_shared.py`.
DEPENDS:  graph_os.types, graph_os.backend, graph_os.backends.*.
NOTES:    The tool layer is backend-agnostic — it calls GraphBackend
          and lets the factory pick Kuzu vs SQLite. Fail-loud on
          backend errors per plan §12.5.
"""

from __future__ import annotations

import difflib
import logging
import re
import sys
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from ..backend import BackendUnavailable, GraphBackend, get_backend
from ..types import GraphEdge, GraphNode

logger = logging.getLogger("graph_os.tools.graph")


# ---------------------------------------------------------------------------
# Envelope helpers — shared with thinking_os via sys.path.
# ---------------------------------------------------------------------------


def _envelope_module():
    try:
        from tools import _shared  # type: ignore
        return _shared
    except ImportError:
        here = Path(__file__).resolve()
        candidate = here.parent.parent.parent / "thinking_os"
        if candidate.exists() and str(candidate) not in sys.path:
            sys.path.insert(0, str(candidate))
        from tools import _shared  # type: ignore
        return _shared


def _ok(data: dict[str, Any], meta: dict[str, Any] | None = None) -> dict[str, Any]:
    shared = _envelope_module()
    merged = {"layer": "graph", **(meta or {})}
    return shared.ok(data, meta=merged)


def _fail(
    category: str,
    message: str,
    *,
    retryable: bool | None = None,
) -> dict[str, Any]:
    shared = _envelope_module()
    return shared.fail(category, message, retryable=retryable)


# ---------------------------------------------------------------------------
# Backend handle — lazy, shared, re-openable.
# ---------------------------------------------------------------------------


_BACKEND_SINGLETON: GraphBackend | None = None


def _backend(*, backend: str | None = None) -> GraphBackend:
    """Return the shared GraphBackend instance.

    B7: close the previous backend before replacing the singleton when the
    caller asks for a different backend, so file handles / DB connections
    don't leak across the swap.
    """
    global _BACKEND_SINGLETON
    if _BACKEND_SINGLETON is None or backend is not None:
        if _BACKEND_SINGLETON is not None:
            try:
                _BACKEND_SINGLETON.close()
            except Exception as exc:  # noqa: BLE001 — swap must not raise
                logger.debug("previous backend close suppressed: %s", exc)
        _BACKEND_SINGLETON = get_backend(backend=backend)
    return _BACKEND_SINGLETON


def reset_backend() -> None:
    """Test-only: drop the cached backend so tests get a fresh one."""
    global _BACKEND_SINGLETON
    if _BACKEND_SINGLETON is not None:
        _BACKEND_SINGLETON.close()
    _BACKEND_SINGLETON = None


# ---------------------------------------------------------------------------
# Shared retrieval helpers
# ---------------------------------------------------------------------------


@dataclass
class NodeSummary:
    uid: str
    kind: str
    label: str
    file_path: str | None
    start_line: int | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "uid": self.uid,
            "kind": self.kind,
            "label": self.label,
            "file_path": self.file_path,
            "start_line": self.start_line,
        }

    @classmethod
    def from_node(cls, node: GraphNode) -> "NodeSummary":
        return cls(
            uid=node.uid,
            kind=node.kind,
            label=node.label,
            file_path=node.file_path,
            start_line=node.start_line,
        )


def _edge_to_dict(edge: GraphEdge, *, include_evidence: bool = False) -> dict[str, Any]:
    # TASK-122: surface provenance derived from extractor — additive,
    # never replaces the existing extractor field.  Hub UI consumers
    # (ImpactPanel, ContextPanel) can colour or filter by this label
    # without parsing extractor IDs.
    from ..types import provenance_for

    out: dict[str, Any] = {
        "source_uid": edge.source_uid,
        "target_uid": edge.target_uid,
        "edge_type": edge.edge_type,
        "confidence": edge.confidence,
        "extractor": edge.extractor,
        "provenance": provenance_for(edge.extractor),
        "source_span": edge.source_span,
    }
    if include_evidence:
        out["evidence"] = [
            {"signal_name": s.signal_name, "weight": s.weight, "note": s.note}
            for s in edge.evidence
        ]
    return out


def _walk_bfs(
    backend: GraphBackend,
    *,
    root_uid: str,
    direction: str,
    max_hops: int,
    confidence_min: float,
    edge_types: Sequence[str] | None,
    visit_limit: int = 500,
) -> tuple[list[GraphNode], list[GraphEdge]]:
    """BFS traversal — shared by context / impact / trace.

    direction: "out" (source→target), "in" (target→source), or "both".

    B2: edges are only recorded the first time they lead to an unseen
    neighbour — this stops duplicate edges piling up when a neighbour is
    reached through multiple predecessors. Edges already traversed from
    either direction via the (source, target, edge_type, extractor)
    identity are suppressed.
    B6: uses ``get_nodes_bulk`` on the frontier instead of one get_node
    per neighbour, collapsing the N+1 pattern.
    """
    edges_out: list[GraphEdge] = []
    seen_edge_ids: set[tuple[str, str, str, str]] = set()
    root_nodes = _bulk_nodes(backend, [root_uid])
    root_node = root_nodes.get(root_uid)
    if root_node is None:
        return [], []

    seen_nodes: dict[str, GraphNode] = {root_uid: root_node}
    visited_uids: set[str] = {root_uid}
    queue: deque[tuple[str, int]] = deque([(root_uid, 0)])

    while queue and len(seen_nodes) < visit_limit:
        uid, depth = queue.popleft()
        if depth >= max_hops:
            continue
        neighbours: list[GraphEdge] = []
        if direction in ("out", "both"):
            neighbours.extend(
                backend.list_edges(
                    source_uid=uid,
                    edge_types=edge_types,
                    confidence_min=confidence_min,
                    limit=visit_limit,
                )
            )
        if direction in ("in", "both"):
            neighbours.extend(
                backend.list_edges(
                    target_uid=uid,
                    edge_types=edge_types,
                    confidence_min=confidence_min,
                    limit=visit_limit,
                )
            )

        frontier_uids: list[str] = []
        frontier_edges: list[GraphEdge] = []
        for edge in neighbours:
            identity = (
                edge.source_uid,
                edge.target_uid,
                edge.edge_type,
                edge.extractor,
            )
            if identity in seen_edge_ids:
                continue
            seen_edge_ids.add(identity)
            next_uid = (
                edge.target_uid if edge.source_uid == uid else edge.source_uid
            )
            # B2: only append when the neighbour is new — stops the edge
            # duplication that happened when the same node was reached
            # via multiple edges from different frontiers.
            if next_uid in visited_uids:
                continue
            frontier_edges.append(edge)
            frontier_uids.append(next_uid)

        if frontier_uids:
            fetched = _bulk_nodes(backend, frontier_uids)
            for edge, next_uid in zip(frontier_edges, frontier_uids):
                node = fetched.get(next_uid)
                if node is None:
                    continue
                edges_out.append(edge)
                if next_uid in visited_uids:
                    continue
                visited_uids.add(next_uid)
                seen_nodes[next_uid] = node
                queue.append((next_uid, depth + 1))
    return list(seen_nodes.values()), edges_out


def _contains_ancestors(
    backend: GraphBackend,
    *,
    leaf_uid: str,
    max_hops: int = 16,
) -> tuple[list[GraphNode], list[GraphEdge]]:
    """Walk the CONTAINS spine from ``leaf_uid`` up to the repo root.

    PURPOSE:      S3 — when ``include_spine=True`` on context/query/export
                  we surface the File→Folder→…→RepoRoot chain so the SPA
                  can render breadcrumbs and the tree-view anchor.
    INPUT:        backend + leaf uid + safety cap.
    OUTPUT:       (ancestor nodes in root→leaf order, edges along the
                  chain in child→parent direction).
    NOTES:        Follows inbound ``contains`` edges one step at a time
                  until no more parent is found or ``max_hops``
                  exhausts. ``folder:`` uids terminate the walk at the
                  repo-root sentinel ``folder:.``.
    """
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []
    seen: set[str] = {leaf_uid}
    current = leaf_uid
    for _ in range(max_hops):
        inbound = backend.list_edges(
            target_uid=current,
            edge_types=("contains",),
            limit=50,
        )
        if not inbound:
            break
        # Pick the first stable parent — spine edges are 1:N on outbound
        # but 1:1 on inbound once de-duplicated; iterate until we find
        # one we haven't visited.
        parent_edge = None
        for edge in inbound:
            if edge.source_uid not in seen:
                parent_edge = edge
                break
        if parent_edge is None:
            break
        parent_uid = parent_edge.source_uid
        seen.add(parent_uid)
        parent_node = backend.get_node(parent_uid)
        if parent_node is None:
            break
        nodes.append(parent_node)
        edges.append(parent_edge)
        current = parent_uid
        if parent_uid == "folder:.":
            break
    # Return root → leaf order so the caller can render breadcrumbs
    # left-to-right.
    nodes.reverse()
    edges.reverse()
    return nodes, edges


def _bulk_nodes(
    backend: GraphBackend, uids: Sequence[str]
) -> dict[str, GraphNode]:
    """B6: prefer backend.get_nodes_bulk; fall back to per-uid for legacy."""
    bulk = getattr(backend, "get_nodes_bulk", None)
    if callable(bulk):
        return bulk(list(uids))
    out: dict[str, GraphNode] = {}
    for uid in uids:
        node = backend.get_node(uid)
        if node is not None:
            out[uid] = node
    return out


# ---------------------------------------------------------------------------
# The 11 tools
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

    PURPOSE:      "find me nodes that look like X" — lexical today
                  (SQLite LIKE / FTS5 on the dogfood backend), hybrid
                  embedding + FTS once Phase I.1's BGE-M3 is ready.
    INPUT:        q (non-empty), optional kind filter, limit, depth +
                  confidence floor for the graph-walk expansion.
    OUTPUT:       ok({results: [NodeSummary + confidence + path]}).
    DEPENDS:      GraphBackend.
    """
    if not q or not q.strip():
        return _fail("validation", "query must be a non-empty string")
    try:
        be = _backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)

    kinds_filter = tuple(kinds) if kinds else None
    nodes = _lexical_search(
        be, q=q, kinds=kinds_filter, limit=limit, max_hops=max_hops
    )
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
        for result_dict, node in zip(results, nodes):
            ancestors, _ = _contains_ancestors(be, leaf_uid=node.uid)
            result_dict["spine"] = [
                NodeSummary.from_node(a).to_dict() for a in ancestors
            ]
    # B22: cap meta.query to 500 chars with ellipsis suffix so the
    # envelope stays bounded regardless of how long the query string is.
    _MAX_QUERY_META = 500
    query_meta = q if len(q) <= _MAX_QUERY_META else q[:_MAX_QUERY_META] + "..."
    return _ok(
        {"results": results[:limit]},
        meta={
            "query": query_meta,
            "backend": be.backend_id,
            "include_spine": include_spine,
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
    backend: str | None = None,
) -> dict[str, Any]:
    """Neighbourhood around a node.

    PURPOSE:      "what does this symbol depend on / who depends on it?"
                  The primary F5 Pre-Implementation tool (plan §14).
    INPUT:        uid or fuzzy label, direction, depth, optional
                  inclusion flags.
    OUTPUT:       ok({node, edges, neighbours, grouped_by_type}).
    """
    try:
        be = _backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)

    root = be.get_node(uid_or_name) or _fuzzy_resolve(be, uid_or_name)
    if root is None:
        return _fail("not_found", f"no node matching {uid_or_name!r}")

    nodes, edges = _walk_bfs(
        be,
        root_uid=root.uid,
        direction=direction,
        max_hops=max(1, int(depth)),
        confidence_min=0.0,
        edge_types=None,
    )
    grouped: dict[str, list[dict[str, Any]]] = {}
    for e in edges:
        grouped.setdefault(e.edge_type, []).append(
            _edge_to_dict(e, include_evidence=include_evidence)
        )

    # B21: include source content for each node when requested.
    def _node_dict(node: GraphNode) -> dict[str, Any]:
        d = NodeSummary.from_node(node).to_dict()
        if include_content:
            snippet = _read_node_content(node)
            if snippet is not None:
                d["content"] = snippet["content"]
                d["truncated"] = snippet["truncated"]
        return d

    payload: dict[str, Any] = {
        "node": _node_dict(root),
        "neighbours": [_node_dict(n) for n in nodes if n.uid != root.uid],
        "edges_by_type": grouped,
        "edge_count": len(edges),
    }
    if include_spine:
        # S3: surface the CONTAINS-ancestor chain (repo-root → … → leaf)
        # so the SPA can render breadcrumbs alongside the context view.
        ancestors, spine_edges = _contains_ancestors(be, leaf_uid=root.uid)
        payload["spine"] = [NodeSummary.from_node(a).to_dict() for a in ancestors]
        payload["spine_edges"] = [_edge_to_dict(e) for e in spine_edges]
    return _ok(
        payload,
        meta={
            "backend": be.backend_id,
            "depth": depth,
            "direction": direction,
            "include_spine": include_spine,
        },
    )


def cos_graph_impact(
    uid: str,
    *,
    direction: str = "downstream",
    depth: int = 3,
    confidence_min: float = 0.5,
    backend: str | None = None,
) -> dict[str, Any]:
    """Blast-radius: which nodes depend on (or are depended on by) `uid`.

    PURPOSE:      F2 Step 10 Dependency Map. Groups the neighbourhood
                  into risk tiers so F11 refactors can sequence work.
    OUTPUT:       ok({nodes_by_tier, edges}).

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
    try:
        be = _backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)
    root = be.get_node(uid)
    if root is None:
        return _fail("not_found", f"no node with uid {uid!r}")

    walk_direction = {"downstream": "in", "upstream": "out", "both": "both"}.get(
        direction, "in"
    )
    nodes, edges = _walk_bfs(
        be,
        root_uid=root.uid,
        direction=walk_direction,
        max_hops=max(1, int(depth)),
        confidence_min=confidence_min,
        edge_types=None,
    )
    tiers: dict[str, list[dict[str, Any]]] = {
        "will_break": [],
        "should_review": [],
        "context": [],
    }
    for edge in edges:
        bucket = (
            "will_break"
            if edge.confidence >= 0.9
            else ("should_review" if edge.confidence >= 0.5 else "context")
        )
        tiers[bucket].append(_edge_to_dict(edge))

    return _ok(
        {
            "root": NodeSummary.from_node(root).to_dict(),
            "direction": direction,
            "tiers": tiers,
            "impacted_count": max(0, len(nodes) - 1),
        },
        meta={"backend": be.backend_id, "depth": depth, "confidence_min": confidence_min},
    )


def cos_graph_detect_changes(
    *,
    scope: str = "working",
    files: Sequence[str] | None = None,
    analyze_downstream: bool = True,
    backend: str | None = None,
) -> dict[str, Any]:
    """Pre-commit self-review: map changed files to affected graph nodes.

    PURPOSE:      F6 Layer 2 + F9 pre-release diff. In I.8 the file set
                  is passed in (`files=[...]`) since the git wiring
                  lives in the CLI / hook layer. `scope` is forwarded
                  as metadata for the caller's bookkeeping.
    OUTPUT:       ok({files, symbols, downstream_tasks, risk_level}).
    """
    if not files:
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
        be = _backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)

    affected_symbols: list[dict[str, Any]] = []
    downstream_tasks: set[str] = set()
    risk = "low"

    for file_path in files:
        file_uid = f"code:file:{file_path}"
        node = be.get_node(file_uid)
        if node is None:
            continue
        _, edges = _walk_bfs(
            be,
            root_uid=file_uid,
            direction="both",
            max_hops=1,
            confidence_min=0.0,
            edge_types=None,
        )
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
            _, deep_edges = _walk_bfs(
                be,
                root_uid=file_uid,
                direction="in",
                max_hops=3,
                confidence_min=0.6,
                edge_types=None,
            )
            # B15: also collect task uids from the deep (depth-3) walk.
            for deep_edge in deep_edges:
                for uid_candidate in (deep_edge.source_uid, deep_edge.target_uid):
                    if uid_candidate.startswith("task:file:"):
                        downstream_tasks.add(uid_candidate)
            if len(deep_edges) > 20:
                risk = "high"
            elif len(deep_edges) > 5 and risk != "high":
                risk = "medium"

    return _ok(
        {
            "scope": scope,
            "files": list(files),
            "symbols": affected_symbols,
            "downstream_tasks": sorted(downstream_tasks),
            "risk_level": risk,
        },
        meta={"backend": be.backend_id, "analyze_downstream": analyze_downstream},
    )


def cos_graph_trace(
    entry_uid: str,
    *,
    terminals: Sequence[str] = ("return", "exception"),
    max_steps: int = 50,
    backend: str | None = None,
) -> dict[str, Any]:
    """Forward execution walk from an entry point.

    PURPOSE:      F7 Step 2 fault isolation / distributed tracing
                  scaffolding.
    OUTPUT:       ok({steps: [NodeSummary], branches}).
    """
    try:
        be = _backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)
    root = be.get_node(entry_uid)
    start_source = "explicit"
    if root is None:
        # TASK-081: fall back to the highest-scoring entry point whose
        # label / file matches the supplied identifier.  Lets agents
        # call cos_graph_trace("login") without first running a
        # separate query to resolve the uid.
        from .. import entry_points as ep_mod

        ep = ep_mod.best_start_for_query(be, entry_uid)
        if ep is not None:
            root = be.get_node(ep.uid)
            start_source = "entry-point-heuristic"
    if root is None:
        return _fail("not_found", f"no node with uid {entry_uid!r}")

    steps: list[dict[str, Any]] = []
    branches: list[dict[str, Any]] = []
    seen: set[str] = set()
    stack: list[str] = [root.uid]
    while stack and len(steps) < max_steps:
        uid = stack.pop()
        if uid in seen:
            continue
        seen.add(uid)
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
            branches.append(
                {
                    "from": uid,
                    "fan_out": [e.target_uid for e in edges],
                }
            )
        for edge in edges:
            if edge.target_uid not in seen:
                stack.append(edge.target_uid)
    return _ok(
        {
            "entry": NodeSummary.from_node(root).to_dict(),
            "steps": steps,
            "branches": branches,
            "terminals": list(terminals),
            "start_source": start_source,
        },
        meta={
            "backend": be.backend_id,
            "step_count": len(steps),
            "start_source": start_source,
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
        be = _backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)
    root = be.get_node(uid)
    if root is None:
        return _fail("not_found", f"no node with uid {uid!r}")

    # B13: use sample_nodes for an unbiased candidate pool.
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

    candidates = [n for n in raw_candidates if n.uid != uid]

    scored = []
    reference = f"{root.label or ''} {root.signature or ''} {root.doc_blob or ''}"
    for node in candidates:
        other = f"{node.label or ''} {node.signature or ''} {node.doc_blob or ''}"
        ratio = difflib.SequenceMatcher(None, reference, other).ratio()
        if ratio >= confidence_min:
            scored.append((ratio, node))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    results = [
        {**NodeSummary.from_node(n).to_dict(), "similarity": round(r, 4)}
        for r, n in scored[: max(1, top_k)]
    ]
    return _ok(
        {"root": NodeSummary.from_node(root).to_dict(), "results": results},
        meta={"backend": be.backend_id, "scorer": "difflib-baseline"},
    )


def cos_graph_references(
    uid: str,
    *,
    kinds: Sequence[str] = ("calls", "accesses_field", "imports", "references_doc"),
    limit: int = 100,
    backend: str | None = None,
) -> dict[str, Any]:
    """Inbound edges to `uid` — "who references this?"."""
    try:
        be = _backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)
    node = be.get_node(uid)
    if node is None:
        return _fail("not_found", f"no node with uid {uid!r}")

    edges = be.list_edges(target_uid=uid, edge_types=tuple(kinds), limit=limit)
    return _ok(
        {
            "node": NodeSummary.from_node(node).to_dict(),
            "references": [_edge_to_dict(e) for e in edges],
            "count": len(edges),
        },
        meta={"backend": be.backend_id, "kinds": list(kinds)},
    )


def cos_graph_path(
    source_uid: str,
    target_uid: str,
    *,
    max_hops: int = 5,
    backend: str | None = None,
) -> dict[str, Any]:
    """Shortest path between two nodes (any direction).

    B4: each hop pulls up to 1000 edges from the backend (up from 200).
    When either side's edge list hits that cap the result is flagged
    ``meta.truncated=True`` so callers know the search may have missed a
    shorter path that lives beyond the first 1000 neighbours.
    """
    try:
        be = _backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)
    if be.get_node(source_uid) is None:
        return _fail("not_found", f"source uid {source_uid!r}")
    if be.get_node(target_uid) is None:
        return _fail("not_found", f"target uid {target_uid!r}")
    _PATH_HOP_LIMIT = 1000
    truncated = False
    parents: dict[str, tuple[str, GraphEdge] | None] = {source_uid: None}
    queue: deque[tuple[str, int]] = deque([(source_uid, 0)])
    while queue:
        uid, depth = queue.popleft()
        if uid == target_uid:
            break
        if depth >= max_hops:
            continue
        out_edges = be.list_edges(source_uid=uid, limit=_PATH_HOP_LIMIT)
        if len(out_edges) >= _PATH_HOP_LIMIT:
            truncated = True
        for edge in out_edges:
            nxt = edge.target_uid
            if nxt not in parents:
                parents[nxt] = (uid, edge)
                queue.append((nxt, depth + 1))
        in_edges = be.list_edges(target_uid=uid, limit=_PATH_HOP_LIMIT)
        if len(in_edges) >= _PATH_HOP_LIMIT:
            truncated = True
        for edge in in_edges:
            nxt = edge.source_uid
            if nxt not in parents:
                parents[nxt] = (uid, edge)
                queue.append((nxt, depth + 1))
    if target_uid not in parents:
        return _ok(
            {"path": None, "edges": [], "truncated": truncated},
            meta={
                "backend": be.backend_id,
                "reason": "unreachable",
                "truncated": truncated,
                "hop_limit": _PATH_HOP_LIMIT,
            },
        )
    chain: list[GraphEdge] = []
    cur = target_uid
    while parents.get(cur) is not None:
        prev, edge = parents[cur]  # type: ignore[misc]
        chain.append(edge)
        cur = prev
    chain.reverse()
    return _ok(
        {
            "path": [source_uid] + [e.target_uid if e.source_uid == source_uid else e.source_uid for e in chain],
            "edges": [_edge_to_dict(e) for e in chain],
            "hops": len(chain),
            "truncated": truncated,
        },
        meta={
            "backend": be.backend_id,
            "truncated": truncated,
            "hop_limit": _PATH_HOP_LIMIT,
        },
    )


def cos_graph_export(
    *,
    format: str = "json",
    root_uid: str | None = None,
    edge_types: Sequence[str] | None = None,
    max_nodes: int = 500,
    include_spine: bool = False,
    backend: str | None = None,
) -> dict[str, Any]:
    """Export a subgraph in `json | mermaid | dot`."""
    try:
        be = _backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)
    if format not in {"json", "mermaid", "dot"}:
        return _fail("validation", f"unknown format {format!r}")

    if root_uid is not None:
        nodes, edges = _walk_bfs(
            be,
            root_uid=root_uid,
            direction="both",
            max_hops=3,
            confidence_min=0.0,
            edge_types=edge_types,
            visit_limit=max_nodes,
        )
    else:
        edges = be.list_edges(edge_types=edge_types, limit=max_nodes)
        node_uids: set[str] = set()
        for e in edges:
            node_uids.add(e.source_uid)
            node_uids.add(e.target_uid)
        nodes = [n for n in (be.get_node(u) for u in node_uids) if n is not None]

    # S3: when include_spine is set, extend the subgraph with the
    # CONTAINS-ancestor chain of the root (or the deepest file node
    # present when no root is specified) so the tree-view has a
    # connected Folder→...→leaf backbone.
    if include_spine:
        seed_uid = root_uid
        if seed_uid is None:
            for n in nodes:
                if (n.kind or "").startswith(("file", "code:file", "doc:file")):
                    seed_uid = n.uid
                    break
        if seed_uid:
            ancestors, spine_edges = _contains_ancestors(be, leaf_uid=seed_uid)
            existing_uids = {n.uid for n in nodes}
            for a in ancestors:
                if a.uid not in existing_uids:
                    nodes.append(a)
                    existing_uids.add(a.uid)
            edges = list(edges) + list(spine_edges)

    if format == "json":
        payload: dict[str, Any] = {
            "format": "json",
            "nodes": [NodeSummary.from_node(n).to_dict() for n in nodes],
            "edges": [_edge_to_dict(e) for e in edges],
        }
    elif format == "mermaid":
        payload = {"format": "mermaid", "diagram": _to_mermaid(nodes, edges)}
    else:  # dot
        payload = {"format": "dot", "diagram": _to_dot(nodes, edges)}
    return _ok(
        payload,
        meta={
            "backend": be.backend_id,
            "node_count": len(nodes),
            "edge_count": len(edges),
            "include_spine": include_spine,
        },
    )


def cos_graph_rename_plan(
    uid: str,
    new_name: str,
    *,
    check_strings: bool = True,
    backend: str | None = None,
) -> dict[str, Any]:
    """Produce a rename plan — call-sites, docs, tests, strings."""
    if not new_name or not new_name.strip():
        return _fail("validation", "new_name must be non-empty")
    try:
        be = _backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)
    root = be.get_node(uid)
    if root is None:
        return _fail("not_found", f"no node with uid {uid!r}")

    call_sites = [
        _edge_to_dict(e)
        for e in be.list_edges(target_uid=uid, edge_types=("calls", "accesses_field", "imports"), limit=500)
    ]
    doc_refs = [
        _edge_to_dict(e)
        for e in be.list_edges(target_uid=uid, edge_types=("links_to", "cites_heading", "references_doc"), limit=500)
    ]
    test_refs = [
        _edge_to_dict(e)
        for e in be.list_edges(target_uid=uid, edge_types=("tested_by",), limit=500)
    ]
    risk = "high" if len(call_sites) > 20 else "medium" if call_sites else "low"

    return _ok(
        {
            "old_name": root.label,
            "new_name": new_name,
            "uid": root.uid,
            "call_sites": call_sites,
            "doc_references": doc_refs,
            "test_references": test_refs,
            "string_literals": [] if not check_strings else _grep_string_literals(root.label or ""),
            "risk": risk,
            "suggested_order": [
                "tests first",
                "implementation",
                "docs",
                "string literals last",
            ],
            "confidence": 0.9 if call_sites else 0.6,
        },
        meta={"backend": be.backend_id},
    )


def cos_graph_contracts(
    *,
    scope: str = "all",
    kinds: Sequence[str] = ("http", "mcp", "grpc", "event", "websocket"),
    backend: str | None = None,
) -> dict[str, Any]:
    """API surface — enumerate every route / tool / event handler."""
    try:
        be = _backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)

    buckets: dict[str, list[dict[str, Any]]] = {
        "http_routes": [],
        "mcp_tools": [],
        "grpc_endpoints": [],
        "event_handlers": [],
        "websocket": [],
    }
    for edge_type in ("handles_route", "handles_tool", "handles_event"):
        for edge in be.list_edges(edge_types=(edge_type,), limit=2000):
            node = be.get_node(edge.target_uid)
            if node is None:
                continue
            kind = (node.metadata or {}).get("kind", "http")
            if kind not in kinds:
                continue
            bucket_key = {
                "http": "http_routes",
                "mcp": "mcp_tools",
                "grpc": "grpc_endpoints",
                "event": "event_handlers",
                "websocket": "websocket",
            }.get(kind, "http_routes")
            buckets[bucket_key].append(
                {
                    **NodeSummary.from_node(node).to_dict(),
                    "method": (node.metadata or {}).get("method"),
                    "path": (node.metadata or {}).get("path"),
                    "framework": (node.metadata or {}).get("framework"),
                    "handler": (node.metadata or {}).get("handler"),
                    "source": edge.source_uid,
                    "confidence": edge.confidence,
                }
            )
    return _ok(
        {"scope": scope, **buckets, "count": sum(len(v) for v in buckets.values())},
        meta={"backend": be.backend_id, "kinds": list(kinds)},
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_node_content(node: GraphNode, *, cap: int = 2000) -> dict[str, Any] | None:
    """B21: read source snippet for a node from its file_path + line range.

    PURPOSE:  Inline source text so ``cos_graph_context(include_content=True)``
              returns a ``content`` field per node without extra round-trips.
    INPUT:    node with file_path, start_line, end_line set.
              cap — max chars to include (default 2000).
    OUTPUT:   dict with ``content`` (str) and ``truncated`` (bool), or None
              when the file is missing or the node has no file_path.
    NOTES:    Silently returns None on any IO error — callers must handle None.
    """
    if not node.file_path:
        return None
    try:
        src = Path(node.file_path)
        if not src.is_file():
            return None
        lines = src.read_text(encoding="utf-8", errors="replace").splitlines()
        start = max(0, (node.start_line or 1) - 1)  # 1-indexed → 0-indexed
        end = (node.end_line or node.start_line or len(lines))
        snippet = "\n".join(lines[start:end])
        truncated = len(snippet) > cap
        return {"content": snippet[:cap], "truncated": truncated}
    except Exception as exc:  # noqa: BLE001 — skip safely on any IO error
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


def _lexical_search(
    backend: GraphBackend,
    *,
    q: str,
    kinds: Sequence[str] | None,
    limit: int,
    max_hops: int,
) -> list[GraphNode]:
    lower = q.lower()
    seen: dict[str, GraphNode] = {}
    for edge in backend.list_edges(limit=1000):
        for side in (edge.source_uid, edge.target_uid):
            if side in seen:
                continue
            node = backend.get_node(side)
            if node is None:
                continue
            if kinds and node.kind not in kinds:
                continue
            haystack = " ".join(
                filter(
                    None,
                    [node.uid, node.label, node.signature, node.doc_blob],
                )
            ).lower()
            if lower in haystack:
                seen[side] = node
            if len(seen) >= limit * 3:
                break
    scored = sorted(
        seen.values(),
        key=lambda n: difflib.SequenceMatcher(None, lower, (n.label or "").lower()).ratio(),
        reverse=True,
    )
    return scored[:limit]


def _grep_string_literals(name: str) -> list[dict[str, Any]]:
    """Stub for the string-scan path. Real implementation lives in CLI layer."""
    return []


def _to_mermaid(nodes: Iterable[GraphNode], edges: Iterable[GraphEdge]) -> str:
    lines = ["graph LR"]
    for n in nodes:
        lines.append(f'  {_safe_id(n.uid)}["{_escape(n.label or n.uid)}"]')
    for e in edges:
        lines.append(
            f"  {_safe_id(e.source_uid)} -->|{e.edge_type}| {_safe_id(e.target_uid)}"
        )
    return "\n".join(lines)


def _to_dot(nodes: Iterable[GraphNode], edges: Iterable[GraphEdge]) -> str:
    lines = ["digraph G {"]
    for n in nodes:
        lines.append(f'  "{_safe_id(n.uid)}" [label="{_escape(n.label or n.uid)}"]')
    for e in edges:
        lines.append(
            f'  "{_safe_id(e.source_uid)}" -> "{_safe_id(e.target_uid)}" '
            f'[label="{e.edge_type}"]'
        )
    lines.append("}")
    return "\n".join(lines)


def _safe_id(uid: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", uid)[:60]


def _escape(text: str) -> str:
    return text.replace("\"", "'")


def cos_graph_entrypoints(
    *,
    top: int = 20,
    kind: str | None = None,
    min_score: float = 0.05,
    backend: str | None = None,
) -> dict[str, Any]:
    """Return scored entry-point candidates (TASK-081).

    PURPOSE:    Surface high-value starting nodes for traces / Hub UI.
    INPUT:      ``top`` — max rows returned (1-200).
                ``kind`` — optional filter on entry_kind
                          (main / cli / http / cron / test).
                ``min_score`` — drop rows below this score.
    OUTPUT:     ok({entrypoints: [{uid, kind, score, label, file_path,
                start_line, components}]}). Empty list when no
                candidates pass the threshold.
    """
    if not isinstance(top, int) or top <= 0:
        return _fail("validation", "top must be a positive int")
    if top > 200:
        top = 200
    if kind is not None and kind not in ("main", "cli", "http", "cron", "test"):
        return _fail(
            "validation",
            f"kind must be one of main/cli/http/cron/test (got {kind!r})",
        )
    try:
        be = _backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)

    from .. import entry_points as ep_mod  # local import: avoids cycle on cold load

    eps = ep_mod.discover(be, min_score=float(min_score), kind_filter=kind)
    rows = [ep.to_dict() for ep in eps[:top]]
    return _ok(
        {"entrypoints": rows},
        meta={
            "backend": be.backend_id,
            "count": len(rows),
            "scanned_kinds": list(("code:function", "code:method", "function", "method")),
        },
    )


__all__ = [
    "cos_graph_query",
    "cos_graph_context",
    "cos_graph_impact",
    "cos_graph_detect_changes",
    "cos_graph_trace",
    "cos_graph_similar",
    "cos_graph_references",
    "cos_graph_path",
    "cos_graph_export",
    "cos_graph_rename_plan",
    "cos_graph_contracts",
    "cos_graph_entrypoints",
    "reset_backend",
]
