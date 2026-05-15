"""graph_os — process-grouped search via Louvain communities (TASK-075)."""

from __future__ import annotations

import logging
import math
from dataclasses import asdict, dataclass, field
from typing import Any

from .backend import GraphBackend
from .types import GraphNode

logger = logging.getLogger("graph_os.communities")


# Edge types that imply a "this calls / depends on that" relationship.
# Communities reflect functional cohesion, not the CONTAINS spine.
_PROCESS_EDGE_TYPES: tuple[str, ...] = (
    "calls",
    "imports",
    "dispatches",
    "handles_route",
    "handles_event",
    "handles_tool",
    "constructs",
    "inherits_from",
    "implements",
)

# Node kinds that can be cluster members.  Filter out folder/file/import
# stubs so processes name themselves after real symbols.
_PROCESS_MEMBER_KINDS: frozenset[str] = frozenset({
    "code:function",
    "function",
    "code:method",
    "method",
    "code:class",
    "class",
    "cos:mcp_tool",
    "mcp_tool",
    "cos:route",
    "route",
})


@dataclass(frozen=True)
class Community:
    """One detected process / community."""

    community_id: str       # stable hash of sorted member uids
    name: str               # anchor function name + suffix
    summary: str            # 1-line: top-3 member labels joined
    priority: float         # log10(size+1) * avg(entry_score)
    member_count: int
    members: tuple[dict[str, Any], ...]  # [{uid, label, kind, step_index}]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Lazy cache (per backend + edge-count signature)
# ---------------------------------------------------------------------------


@dataclass
class _CacheEntry:
    signature: tuple[str, int]
    communities: list[Community]
    membership: dict[str, str]  # node_uid → community_id


_CACHE: dict[str, _CacheEntry] = {}


def reset_cache() -> None:
    """Clear the community cache. Used by tests + cos sync-doctor --repair."""
    _CACHE.clear()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_communities(
    backend: GraphBackend,
    *,
    min_size: int = 2,
    max_communities: int = 200,
) -> tuple[list[Community], dict[str, str]]:
    """Return ``(communities, membership)``.

    Caching: keyed by ``(backend_id, edge_count(`calls`+`imports`))``.
    First call after a reindex computes; subsequent calls within the
    same edge-count window reuse the result.
    """
    signature = _signature(backend)
    cached = _CACHE.get(backend.backend_id)
    if cached is not None and cached.signature == signature:
        return cached.communities, cached.membership

    nodes_by_uid, edges = _load_subgraph(backend)
    if not nodes_by_uid or not edges:
        result: tuple[list[Community], dict[str, str]] = ([], {})
        _CACHE[backend.backend_id] = _CacheEntry(signature, [], {})
        return result

    communities = _detect_communities(
        nodes_by_uid=nodes_by_uid,
        edges=edges,
        min_size=min_size,
        max_communities=max_communities,
        backend=backend,
    )
    membership: dict[str, str] = {}
    for c in communities:
        for m in c.members:
            membership[m["uid"]] = c.community_id

    _CACHE[backend.backend_id] = _CacheEntry(signature, communities, membership)
    return communities, membership


def communities_to_processes(
    communities: list[Community],
    relevant_uids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Filter `communities` down to those that contain at least one of
    ``relevant_uids`` (i.e. matched by the lexical search) and return
    them as JSON-serialisable dicts ready for `cos_graph_query`.

    When ``relevant_uids`` is None, every community is returned (used
    by `cos_graph_communities`).
    """
    out: list[dict[str, Any]] = []
    for c in communities:
        if relevant_uids is not None:
            uids_in_community = {m["uid"] for m in c.members}
            if not (uids_in_community & relevant_uids):
                continue
        out.append(c.to_dict())
    return out


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _signature(backend: GraphBackend) -> tuple[str, int]:
    """Cache key — invalidates whenever the call/import edge count
    changes.  Cheap (~one COUNT(*) per type)."""
    edge_count = sum(backend.count_edges(t) for t in ("calls", "imports"))
    return (backend.backend_id, int(edge_count))


def _load_subgraph(
    backend: GraphBackend,
) -> tuple[dict[str, GraphNode], list[tuple[str, str]]]:
    """Pull every node + every process edge into memory once.

    The cap (50_000 edges) protects against pathological repos; if a
    repo exceeds it we degrade to "no communities" rather than blow
    memory.  Real coding-os graphs sit at ~10k edges.
    """
    nodes_by_uid: dict[str, GraphNode] = {}
    edges: list[tuple[str, str]] = []
    for kind in _PROCESS_MEMBER_KINDS:
        for n in backend.sample_nodes(kind=kind, limit=50_000):
            nodes_by_uid[n.uid] = n

    for et in _PROCESS_EDGE_TYPES:
        for e in backend.list_edges(edge_types=(et,), limit=50_000):
            if e.source_uid in nodes_by_uid and e.target_uid in nodes_by_uid:
                edges.append((e.source_uid, e.target_uid))
    return nodes_by_uid, edges


def _detect_communities(
    *,
    nodes_by_uid: dict[str, GraphNode],
    edges: list[tuple[str, str]],
    min_size: int,
    max_communities: int,
    backend: GraphBackend,
) -> list[Community]:
    """Run Louvain (or fall back to greedy modularity) and produce
    Community records sorted by priority desc."""
    try:
        import networkx as nx  # type: ignore
    except ImportError:
        logger.debug("networkx unavailable — communities disabled")
        return []

    g = nx.Graph()
    for uid in nodes_by_uid:
        g.add_node(uid)
    for src, dst in edges:
        if src == dst:
            continue
        g.add_edge(src, dst)

    if g.number_of_edges() == 0:
        return []

    detector = _pick_detector(nx)
    if detector is None:
        return []
    try:
        clusters = detector(g)
    except Exception as exc:  # noqa: BLE001 — community libs raise creatively
        logger.debug("community detection failed: %s", exc)
        return []

    # Score entry points (TASK-081) once so process priority is
    # deterministic.  Import lazily to avoid a cold-load cycle and
    # tolerate the WIP entry_points module being absent — community
    # detection still produces a useful result without entry-point
    # scoring (priority just degrades to step-count order).
    eps: dict[str, float] = {}
    try:
        from . import entry_points  # type: ignore[attr-defined]

        eps = {
            ep.uid: ep.score
            for ep in entry_points.discover(backend, min_score=0.0)
        }
    except ImportError as exc:
        logger.debug("entry_points unavailable; priority degrades: %s", exc)

    out: list[Community] = []
    for cluster in clusters:
        members = [nodes_by_uid[uid] for uid in cluster if uid in nodes_by_uid]
        if len(members) < min_size:
            continue
        ordered = _step_order(members, edges_lookup=set(edges), entry_scores=eps)
        anchor = ordered[0] if ordered else members[0]
        priority = _priority_for(ordered, eps)
        community = Community(
            community_id=_community_id(ordered),
            name=_community_name(anchor),
            summary=_community_summary(ordered),
            priority=priority,
            member_count=len(ordered),
            members=tuple(
                {
                    "uid": m.uid,
                    "label": m.label or m.uid,
                    "kind": m.kind,
                    "step_index": idx,
                    "file_path": m.file_path,
                    "start_line": m.start_line,
                }
                for idx, m in enumerate(ordered)
            ),
        )
        out.append(community)

    out.sort(key=lambda c: (-c.priority, c.community_id))
    return out[:max_communities]


def _pick_detector(nx: Any):  # type: ignore[no-untyped-def]
    community = getattr(nx, "community", None) or getattr(
        nx.algorithms, "community", None  # type: ignore[attr-defined]
    )
    if community is None:
        return None
    if hasattr(community, "louvain_communities"):
        return community.louvain_communities  # type: ignore[no-any-return]
    if hasattr(community, "greedy_modularity_communities"):
        return community.greedy_modularity_communities  # type: ignore[no-any-return]
    return None


def _step_order(
    members: list[GraphNode],
    *,
    edges_lookup: set[tuple[str, str]],
    entry_scores: dict[str, float],
) -> list[GraphNode]:
    """DFS from the highest-entry-score anchor; tie-break by file path."""
    if not members:
        return []
    members_sorted = sorted(
        members,
        key=lambda m: (-entry_scores.get(m.uid, 0.0), m.file_path or "", m.uid),
    )
    member_uids = {m.uid for m in members}
    by_uid = {m.uid: m for m in members}

    visited: set[str] = set()
    order: list[GraphNode] = []
    stack: list[str] = [members_sorted[0].uid]
    while stack:
        uid = stack.pop()
        if uid in visited:
            continue
        visited.add(uid)
        node = by_uid.get(uid)
        if node is None:
            continue
        order.append(node)
        # Push neighbours (intra-community only) with stable order.
        nexts = sorted(
            tgt
            for src, tgt in edges_lookup
            if src == uid and tgt in member_uids and tgt not in visited
        )
        for nxt in reversed(nexts):
            stack.append(nxt)
    # Append unreachable members (graph may be disconnected within a
    # cluster); preserves invariant that every member appears once.
    for m in members_sorted:
        if m.uid not in visited:
            order.append(m)
    return order


def _priority_for(
    members: list[GraphNode],
    entry_scores: dict[str, float],
) -> float:
    if not members:
        return 0.0
    avg_entry = sum(entry_scores.get(m.uid, 0.0) for m in members) / len(members)
    return round(math.log10(len(members) + 1) * (avg_entry + 0.1), 4)


def _community_id(members: list[GraphNode]) -> str:
    """Stable id derived from sorted member uids (so the same cluster
    keeps its id across runs even when scores shift slightly)."""
    import hashlib

    if not members:
        return "community:empty"
    sorted_uids = sorted(m.uid for m in members)
    digest = hashlib.sha1("|".join(sorted_uids).encode("utf-8")).hexdigest()[:12]
    return f"community:{digest}"


def _community_name(anchor: GraphNode) -> str:
    """Pick the anchor's label as the community name; fall back to the
    last segment of its uid."""
    label = (anchor.label or "").strip()
    if label:
        return f"{label}-flow"
    tail = anchor.uid.split("::")[-1] or anchor.uid
    return f"{tail}-flow"


def _community_summary(members: list[GraphNode]) -> str:
    """1-line: top 3 member labels joined with ' → '. No LLM needed."""
    labels = []
    for m in members[:3]:
        l = (m.label or m.uid.split("::")[-1] or m.uid).strip()
        if l:
            labels.append(l)
    return " → ".join(labels) if labels else ""


__all__ = [
    "Community",
    "compute_communities",
    "communities_to_processes",
    "reset_cache",
]
