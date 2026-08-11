"""Export tools: the community-driven `processes` view.

Private module of graph_os.tools.graph — import via the graph module,
never directly (the kernel imports this file at its bottom).
"""

from __future__ import annotations

from typing import Any

from ..backend import GraphBackend
from ..types import GraphEdge, GraphNode


def _export_processes(
    be: GraphBackend,
    *,
    max_nodes: int,
) -> tuple[list[GraphNode], list[GraphEdge]]:
    """Return the community-driven view (TASK-141 + TASK-075).

    Each Community produces:
      - one synthetic ``cos:community`` node (label = process name)
      - real member nodes (functions / methods / classes)
      - synthetic ``member_of_community`` edges from member → community

    The synthetic nodes / edges are never persisted — they live only
    in the export response so the SPA's `Processes` view has something
    to render without polluting the SQLite tables.
    """
    from .. import communities as comm_mod

    communities, _membership = comm_mod.compute_communities(be, min_size=2)
    if not communities:
        return [], []

    # TASK-407: two-pass fair budget reservation. The old greedy pass
    # walked community-by-community and spent the whole budget on the
    # first (biggest) cluster's members, so at max_nodes=500 only the
    # first ~2 community headers surfaced — the TASK-406 visual rejection.
    # Pass 1 reserves one header node per community (focus+context map
    # needs every group visible). Pass 2 spreads the remaining budget as
    # an EQUAL per-community member quota (top hubs by step_index), so no
    # single 400-member cluster starves the others. Members beyond the
    # quota are dropped — the community-map home shows each subsystem's
    # head plus its top hubs, not every leaf.
    community_nodes: list[GraphNode] = []
    member_nodes_by_uid: dict[str, GraphNode] = {}
    edges: list[GraphEdge] = []

    # Pass 1 — headers (one synthetic node per community, budget-capped).
    headed: list[Any] = []
    for c in communities:
        if len(community_nodes) >= max_nodes:
            break
        community_nodes.append(
            GraphNode(
                uid=c.community_id,
                kind="community",
                label=c.name,
                file_path=None,
                metadata={
                    "summary": c.summary,
                    "priority": c.priority,
                    "member_count": c.member_count,
                    "synthetic": True,
                },
            )
        )
        headed.append(c)

    # Pass 2 — equal-share member quota across the communities that got a
    # header. Floor of 1 so every headed community contributes at least
    # its top hub; the per-community cap is the fair share of what's left.
    member_budget = max(0, max_nodes - len(community_nodes))
    per_community = max(1, member_budget // len(headed)) if headed else 0
    for c in headed:
        if member_budget <= 0:
            break
        taken = 0
        for m in c.members:
            if member_budget <= 0 or taken >= per_community:
                break
            real = be.get_node(m["uid"])
            if real is None:
                continue
            if real.uid not in member_nodes_by_uid:
                member_nodes_by_uid[real.uid] = real
                member_budget -= 1
                taken += 1
            edges.append(
                GraphEdge(
                    source_uid=real.uid,
                    target_uid=c.community_id,
                    edge_type="member_of_community",
                    extractor="communities@v1",
                    confidence=1.0,
                )
            )
    return community_nodes + list(member_nodes_by_uid.values()), edges
