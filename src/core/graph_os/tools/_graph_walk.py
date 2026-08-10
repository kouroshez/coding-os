"""Node summaries, edge shaping, and graph traversal shared by every tool.

Leaf of graph_os.tools.graph — depends only on the envelope leaf.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from ..backend import GraphBackend
from ..types import GraphEdge, GraphNode
from ._graph_envelope import logger

# F4 / F2 / shared: edge types that represent *behavioural* dependency
# (a real call / construction / dispatch / import) — promoting a
# behavioural edge to `will_break` in impact analysis, or counting it
# as a usage site in rename planning. Structural edges (`contains`,
# `tested_by`) are deliberately excluded. Single SSOT shared by
# `cos_graph_impact`, `cos_graph_rename_plan`, and any future tier
# logic — keeps the three call sites in lockstep.
_BEHAVIOURAL_EDGE_TYPES: frozenset[str] = frozenset(
    {
        "calls",
        "imports",
        "constructs",
        "accesses_field",
        "has_param_type",
        "has_return_type",
        "returns_type",
        "inherits_from",
        "implements",
        "dispatches",
        "awaits",
        "is_decorated_by",
        "handles_route",
        "handles_event",
        "handles_tool",
        "references_doc",
    }
)


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
    # Optional centrality / hub score, populated by exporters that
    # have a degree map handy (graph_export, graph_query). None when
    # the caller did not pre-compute degrees.
    degree: int | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "uid": self.uid,
            "kind": self.kind,
            "label": self.label,
            "file_path": self.file_path,
            "start_line": self.start_line,
        }
        if self.degree is not None:
            out["degree"] = self.degree
        return out

    @classmethod
    def from_node(cls, node: GraphNode, *, degree: int | None = None) -> NodeSummary:
        return cls(
            uid=node.uid,
            kind=node.kind,
            label=node.label,
            file_path=node.file_path,
            start_line=node.start_line,
            degree=degree,
        )


def _degree_map_for(backend: GraphBackend, uids: Sequence[str]) -> dict[str, int]:
    """Server-side degree count for a node set.

    Cheaper than the client recomputing on every render: one query per
    export instead of N. Falls back to {} when the backend is not
    SQLite-backed (Kuzu can extend later) so consumers can degrade
    gracefully.
    """
    if not uids:
        return {}
    sqlite_conn = getattr(backend, "_conn", None)
    if sqlite_conn is None:
        return {}
    placeholders = ",".join("?" * len(uids))
    try:
        # Split the OR-join into two index-friendly halves (the OR forced a full
        # edge scan, bypassing idx_graph_edges_source/target). UNION ALL + outer
        # GROUP BY sums in- and out-degree per uid. TASK-228.
        rows = sqlite_conn.execute(
            f"""
            SELECT uid, SUM(cnt) FROM (
                SELECT n.uid AS uid, COUNT(*) AS cnt
                FROM graph_edges_v12 e JOIN graph_nodes n ON n.id = e.source_id
                WHERE n.uid IN ({placeholders}) GROUP BY n.uid
                UNION ALL
                SELECT n.uid AS uid, COUNT(*) AS cnt
                FROM graph_edges_v12 e JOIN graph_nodes n ON n.id = e.target_id
                WHERE n.uid IN ({placeholders}) GROUP BY n.uid
            ) GROUP BY uid
            """,
            tuple(uids) + tuple(uids),
        ).fetchall()
    except Exception as exc:
        logger.debug("degree query suppressed: %s", exc)
        return {}
    return {row[0]: int(row[1]) for row in rows}


def _edge_to_dict(edge: GraphEdge, *, include_evidence: bool = False) -> dict[str, Any]:
    # surface provenance derived from extractor — additive,
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
    exclude_kinds: frozenset[str] = frozenset(),
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
            next_uid = edge.target_uid if edge.source_uid == uid else edge.source_uid
            # B2: only append when the neighbour is new — stops the edge
            # duplication that happened when the same node was reached
            # via multiple edges from different frontiers.
            if next_uid in visited_uids:
                continue
            frontier_edges.append(edge)
            frontier_uids.append(next_uid)

        if frontier_uids:
            fetched = _bulk_nodes(backend, frontier_uids)
            for edge, next_uid in zip(frontier_edges, frontier_uids, strict=False):
                node = fetched.get(next_uid)
                if node is None:
                    continue
                # TASK-403: skip excluded (noise) kinds DURING the walk so
                # they never consume the visit budget — the export used to
                # over-fetch 4× to compensate post-hoc, which quadrupled
                # rooted-walk latency.
                if exclude_kinds and (node.kind or "") in exclude_kinds:
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
    """Walk the CONTAINS spine from ``leaf_uid`` up to the repo root."""
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


def _bulk_nodes(backend: GraphBackend, uids: Sequence[str]) -> dict[str, GraphNode]:
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


def _count_edges_for(
    backend: GraphBackend,
    *,
    target_uid: str | None = None,
    source_uid: str | None = None,
    edge_types: Sequence[str] | None = None,
) -> int:
    """Count edges matching the filter — separate from list_edges so the
    caller can know "you got N of M". Walks SQLite directly when the
    backend exposes ``_conn`` (the production path); falls back to
    pulling a large list and counting it for stub backends (tests).
    """
    sqlite_conn = getattr(backend, "_conn", None)
    if sqlite_conn is not None:
        where = []
        params: list[Any] = []
        if source_uid is not None:
            where.append("n_src.uid = ?")
            params.append(source_uid)
        if target_uid is not None:
            where.append("n_tgt.uid = ?")
            params.append(target_uid)
        if edge_types:
            placeholders = ",".join("?" * len(edge_types))
            where.append(f"e.edge_type IN ({placeholders})")
            params.extend(edge_types)
        clause = ("WHERE " + " AND ".join(where)) if where else ""
        sql = f"""
          SELECT COUNT(*)
          FROM graph_edges_v12 e
          JOIN graph_nodes n_src ON n_src.id = e.source_id
          JOIN graph_nodes n_tgt ON n_tgt.id = e.target_id
          {clause}
        """
        return int(sqlite_conn.execute(sql, params).fetchone()[0])
    # Stub backend path — pull a generous slice and count it.
    edges = backend.list_edges(
        source_uid=source_uid,
        target_uid=target_uid,
        edge_types=tuple(edge_types) if edge_types else None,
        limit=10_000,
    )
    return len(edges)


# edge categories that drive the new view modes.
_SEMANTIC_EDGES: tuple[str, ...] = (
    "calls",
    "imports",
    "inherits_from",
    "implements",
    "extends",
    "dispatches",
    "handles_route",
    "handles_tool",
    "handles_event",
    "constructs",
    "awaits",
    "references",
    "references_doc",
    "is_decorated_by",
)
