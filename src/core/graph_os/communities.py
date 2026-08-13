"""graph_os — process-grouped search via Louvain communities (TASK-075)."""

from __future__ import annotations

import logging
import math
from dataclasses import asdict, dataclass
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
_PROCESS_MEMBER_KINDS: frozenset[str] = frozenset(
    {
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
    }
)


@dataclass(frozen=True)
class Community:
    """One detected process / community."""

    community_id: str  # stable hash of sorted member uids
    name: str  # anchor function name + suffix
    summary: str  # 1-line: top-3 member labels joined
    priority: float  # log10(size+1) * avg(entry_score)
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
    min_size: int
    max_communities: int
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
    # W7.9 / R4-03: cache key MUST include min_size + max_communities,
    # otherwise the first caller's params silently win for the lifetime
    # of the process. Re-detection is cheap (~50 ms) compared to the
    # debug surface of silent param drop.
    if (
        cached is not None
        and cached.signature == signature
        and cached.min_size == min_size
        and cached.max_communities == max_communities
    ):
        return cached.communities, cached.membership

    nodes_by_uid, edges = _load_subgraph(backend)
    if not nodes_by_uid or not edges:
        _CACHE[backend.backend_id] = _CacheEntry(signature, min_size, max_communities, [], {})
        return [], {}

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

    _CACHE[backend.backend_id] = _CacheEntry(
        signature, min_size, max_communities, communities, membership
    )
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
    # Cache key — invalidates whenever the call/import edge count changes.
    edge_count = sum(backend.count_edges(t) for t in ("calls", "imports"))
    return (backend.backend_id, int(edge_count))


_SUBGRAPH_CAP = 50_000


def subgraph_input_truncated(backend: GraphBackend) -> bool:
    """True when the Louvain input would hit the per-type cap — i.e. the
    community map is computed on a partial slice (F12 coverage-honesty)."""
    return any(backend.count_edges(et) >= _SUBGRAPH_CAP for et in _PROCESS_EDGE_TYPES)


def _load_subgraph(
    backend: GraphBackend,
) -> tuple[dict[str, GraphNode], list[tuple[str, str]]]:
    # Above _SUBGRAPH_CAP (per kind/edge-type) clustering is computed on a
    # partial slice — subgraph_input_truncated() surfaces that to the envelope.
    nodes_by_uid: dict[str, GraphNode] = {}
    edges: list[tuple[str, str]] = []
    for kind in _PROCESS_MEMBER_KINDS:
        for n in backend.sample_nodes(kind=kind, limit=_SUBGRAPH_CAP):
            nodes_by_uid[n.uid] = n

    for et in _PROCESS_EDGE_TYPES:
        batch = backend.list_edges(edge_types=(et,), limit=_SUBGRAPH_CAP)
        if len(batch) >= _SUBGRAPH_CAP:
            logger.warning(
                "community subgraph hit cap (%d) on edge_type=%s — clustering is partial",
                _SUBGRAPH_CAP,
                et,
            )
        for e in batch:
            if e.source_uid in nodes_by_uid and e.target_uid in nodes_by_uid:
                edges.append((e.source_uid, e.target_uid))
    return nodes_by_uid, edges


def _is_test_member(node: GraphNode) -> bool:
    # A community member that is test scaffolding rather than production
    # code. Used to down-rank test-flow clusters.
    label = (node.label or "").lower()
    fp = (node.file_path or "").lower()
    kind = (node.kind or "").lower()
    return (
        "test" in kind
        or label.startswith("test_")
        or fp.startswith("tests/")
        or "/tests/" in fp
        or "_test." in fp
        or "/test_" in fp
    )


def _detect_communities(
    *,
    nodes_by_uid: dict[str, GraphNode],
    edges: list[tuple[str, str]],
    min_size: int,
    max_communities: int,
    backend: GraphBackend,
) -> list[Community]:
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
    except Exception as exc:
        logger.debug("community detection failed: %s", exc)
        return []

    # Score entry points once so process priority is
    # deterministic.  Import lazily to avoid a cold-load cycle and
    # tolerate the WIP entry_points module being absent — community
    # detection still produces a useful result without entry-point
    # scoring (priority just degrades to step-count order).
    eps: dict[str, float] = {}
    try:
        from . import entry_points  # type: ignore[attr-defined]

        eps = {ep.uid: ep.score for ep in entry_points.discover(backend, min_score=0.0)}
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
        # down-rank test-flow-dominated clusters so production
        # subsystems surface. Test files have dense intra-file call graphs
        # that otherwise win on size. Scale by production-member fraction:
        # all-test → 0.2x, all-production → 1.0x (unchanged).
        if ordered:
            n_test = sum(1 for m in ordered if _is_test_member(m))
            prod_fraction = 1.0 - n_test / len(ordered)
            priority = round(priority * (0.2 + 0.8 * prod_fraction), 4)
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
        nx.algorithms,
        "community",
        None,  # type: ignore[attr-defined]
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
    # Sorted member uids → same cluster keeps its id across runs even when
    # scores shift slightly.
    import hashlib

    if not members:
        return "community:empty"
    sorted_uids = sorted(m.uid for m in members)
    digest = hashlib.sha1("|".join(sorted_uids).encode("utf-8"), usedforsecurity=False).hexdigest()[
        :12
    ]
    return f"community:{digest}"


def _community_name(anchor: GraphNode) -> str:
    label = (anchor.label or "").strip()
    if label:
        return f"{label}-flow"
    tail = anchor.uid.split("::")[-1] or anchor.uid
    return f"{tail}-flow"


def _community_summary(members: list[GraphNode]) -> str:
    labels = []
    for m in members[:3]:
        label = (m.label or m.uid.split("::")[-1] or m.uid).strip()
        if label:
            labels.append(label)
    return " → ".join(labels) if labels else ""


__all__ = [
    "Community",
    "communities_to_processes",
    "compute_communities",
    "reset_cache",
]
