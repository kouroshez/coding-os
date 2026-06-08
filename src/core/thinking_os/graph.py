"""
Thinking OS — Concept/file dependency graph.

Lightweight adjacency list in SQLite for tracking relationships between
files and concepts. Built incrementally from observation captures.

Edge types:
  - co_edit: files modified in the same session
  - concept_link: concepts co-occurring in learned patterns
"""

from __future__ import annotations

import json
import logging
import sqlite3
from collections import deque

logger = logging.getLogger("thinking_os.graph")


# ---------------------------------------------------------------------------
# Edge recording
# ---------------------------------------------------------------------------


def record_co_edit(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    file_path: str,
    max_links: int = 8,
) -> list[dict]:
    """Create co_edit edges between this file and recent other files in the session.

    Bounded fan-out (contract: docs/engineering/concept-graph.md): links only to
    the `max_links` MOST-RECENTLY-edited other files, so a long multi-file session
    can't create the O(N^2) edge explosion that bloated the graph to 260 MB.
    Recency is also better signal than session-wide pairing.

    Args:
        conn: SQLite connection.
        session_id: Current session identifier.
        file_path: The file just modified.
        max_links: Cap on edges created per call (most-recent other files).

    Returns:
        List of created/updated edges.
    """
    if not session_id or not file_path:
        return []

    # The most-recently-edited OTHER files in this session (bounded fan-out).
    rows = conn.execute(
        "SELECT files_modified, MAX(created_at) AS last_at FROM observations "
        "WHERE session_id = ? AND files_modified != ? AND files_modified IS NOT NULL "
        "GROUP BY files_modified ORDER BY last_at DESC LIMIT ?",
        (session_id, file_path, max(1, max_links)),
    ).fetchall()

    edges = []
    for row in rows:
        other_file = row[0]
        if not other_file:
            continue

        # Normalize edge direction (alphabetical) for consistent dedup
        source, target = sorted([file_path, other_file])

        try:
            conn.execute(
                "INSERT INTO concept_graph (source, target, edge_type, weight, evidence) "
                "VALUES (?, ?, 'co_edit', 1.0, ?) "
                "ON CONFLICT(source, target, edge_type) DO UPDATE SET "
                "weight = weight + 0.1, updated_at = CURRENT_TIMESTAMP",
                (source, target, session_id),
            )
            edges.append({"source": source, "target": target, "edge_type": "co_edit"})
        except sqlite3.OperationalError:
            break  # concept_graph table may not exist (pre-v4)

    if edges:
        conn.commit()
    return edges


def build_concept_links(
    conn: sqlite3.Connection,
    *,
    min_co_occurrence: int = 2,
) -> dict:
    """Batch: scan learned_patterns concepts and build concept_link edges.

    Two concepts get an edge if they co-occur in min_co_occurrence patterns.

    Args:
        conn: SQLite connection.
        min_co_occurrence: Minimum patterns sharing both concepts.

    Returns:
        Dict with edges_created count.
    """
    rows = conn.execute(
        "SELECT id, concepts FROM learned_patterns WHERE concepts IS NOT NULL"
    ).fetchall()

    # Count co-occurrences
    pair_counts: dict[tuple[str, str], int] = {}
    for row in rows:
        try:
            concepts = json.loads(row["concepts"])
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(concepts, list):
            continue
        # All pairs
        for i, c1 in enumerate(concepts):
            for c2 in concepts[i + 1 :]:
                pair = tuple(sorted([str(c1).lower(), str(c2).lower()]))
                pair_counts[pair] = pair_counts.get(pair, 0) + 1

    edges_created = 0
    for (c1, c2), count in pair_counts.items():
        if count < min_co_occurrence:
            continue
        weight = min(5.0, count * 0.5)
        try:
            conn.execute(
                "INSERT INTO concept_graph (source, target, edge_type, weight) "
                "VALUES (?, ?, 'concept_link', ?) "
                "ON CONFLICT(source, target, edge_type) DO UPDATE SET "
                "weight = ?, updated_at = CURRENT_TIMESTAMP",
                (c1, c2, weight, weight),
            )
            edges_created += 1
        except sqlite3.OperationalError:
            break

    conn.commit()
    return {"status": "ok", "edges_created": edges_created, "pairs_analyzed": len(pair_counts)}


# ---------------------------------------------------------------------------
# Graph queries
# ---------------------------------------------------------------------------


def query_related(
    conn: sqlite3.Connection,
    *,
    node: str,
    max_hops: int = 2,
    limit: int = 10,
    edge_types: list[str] | None = None,
) -> dict:
    """BFS traversal from a node, returning related nodes within max_hops.

    Args:
        conn: SQLite connection.
        node: Starting node (file path or concept).
        max_hops: Maximum traversal depth (1-3, default 2).
        limit: Max results (1-50, default 10).
        edge_types: Filter by edge types (co_edit, concept_link). None = all.

    Returns:
        Dict with nodes list and edges.
    """
    max_hops = max(1, min(3, max_hops))
    limit = max(1, min(50, limit))
    node = node.lower().strip()

    visited: set[str] = {node}
    result_nodes: list[dict] = []
    result_edges: list[dict] = []
    queue: deque[tuple[str, int]] = deque([(node, 0)])

    while queue and len(result_nodes) < limit:
        current, depth = queue.popleft()
        if depth >= max_hops:
            continue

        # Build edge type filter
        type_filter = ""
        params: list = [current, current]
        if edge_types:
            placeholders = ",".join("?" for _ in edge_types)
            type_filter = f" AND edge_type IN ({placeholders})"
            params.extend(edge_types * 2)  # once for each half of UNION

        rows = conn.execute(
            f"SELECT target AS neighbor, edge_type, weight FROM concept_graph "
            f"WHERE source = ?{type_filter} "
            f"UNION "
            f"SELECT source AS neighbor, edge_type, weight FROM concept_graph "
            f"WHERE target = ?{type_filter} "
            "ORDER BY weight DESC",
            params,
        ).fetchall()

        for row in rows:
            neighbor = row["neighbor"]
            if neighbor in visited:
                continue
            visited.add(neighbor)

            result_nodes.append(
                {
                    "node": neighbor,
                    "edge_type": row["edge_type"],
                    "weight": row["weight"],
                    "depth": depth + 1,
                }
            )
            result_edges.append(
                {
                    "source": current,
                    "target": neighbor,
                    "edge_type": row["edge_type"],
                    "weight": row["weight"],
                }
            )
            queue.append((neighbor, depth + 1))

    return {
        "root": node,
        "nodes": result_nodes[:limit],
        "edges": result_edges[:limit],
        "count": min(len(result_nodes), limit),
    }


def query_cluster(
    conn: sqlite3.Connection,
    *,
    nodes: list[str],
    limit: int = 15,
) -> dict:
    """Find the subgraph connecting multiple nodes (union of 1-hop neighborhoods).

    Args:
        conn: SQLite connection.
        nodes: List of starting nodes.
        limit: Max edges to return.

    Returns:
        Dict with all edges in the cluster.
    """
    limit = max(1, min(50, limit))
    all_edges: list[dict] = []
    seen_edges: set[tuple[str, str, str]] = set()

    for node in nodes:
        node = node.lower().strip()
        rows = conn.execute(
            "SELECT source, target, edge_type, weight FROM concept_graph "
            "WHERE source = ? OR target = ? "
            "ORDER BY weight DESC LIMIT ?",
            (node, node, limit),
        ).fetchall()

        for row in rows:
            edge_key = (row["source"], row["target"], row["edge_type"])
            if edge_key not in seen_edges:
                seen_edges.add(edge_key)
                all_edges.append(dict(row))

    return {
        "roots": nodes,
        "edges": all_edges[:limit],
        "count": min(len(all_edges), limit),
    }


def prune_stale_edges(
    conn: sqlite3.Connection,
    *,
    max_age_days: int = 90,
    min_weight: float = 0.1,
) -> dict:
    """Remove old or low-weight edges from the graph.

    Args:
        conn: SQLite connection.
        max_age_days: Prune edges older than this.
        min_weight: Prune edges with weight below this.

    Returns:
        Dict with pruned count.
    """
    cursor = conn.execute(
        "DELETE FROM concept_graph "
        "WHERE weight < ? OR updated_at < datetime('now', '-' || ? || ' days')",
        (min_weight, max_age_days),
    )
    conn.commit()
    return {"pruned": cursor.rowcount}
