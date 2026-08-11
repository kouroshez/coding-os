"""Edge-integrity checks: dangling endpoints, duplicates and self loops."""

from __future__ import annotations

import sqlite3
from typing import Any


def _check_edges(sqlite_conn: sqlite3.Connection, *, fix: bool) -> tuple[list[dict[str, Any]], int]:
    issues: list[dict[str, Any]] = []
    fixed_count = 0

    # 1. Dangling source edges (source_id FK points to deleted node)
    dangling_src_rows = sqlite_conn.execute(
        """
        SELECT e.id, ns.uid, nt.uid
        FROM graph_edges_v12 e
        LEFT JOIN graph_nodes ns ON ns.id = e.source_id
        LEFT JOIN graph_nodes nt ON nt.id = e.target_id
        WHERE ns.id IS NULL
        LIMIT 100
        """
    ).fetchall()
    dangling_src_count = sqlite_conn.execute(
        """
        SELECT COUNT(*) FROM graph_edges_v12 e
        LEFT JOIN graph_nodes ns ON ns.id = e.source_id
        WHERE ns.id IS NULL
        """
    ).fetchone()[0]
    if dangling_src_count:
        issues.append(
            {
                "category": "dangling_source",
                "count": dangling_src_count,
                "sample": [
                    {"edge_id": r[0], "source_uid": r[1], "target_uid": r[2]}
                    for r in dangling_src_rows[:5]
                ],
            }
        )
        if fix:
            ids_to_del = [r[0] for r in dangling_src_rows]
            if ids_to_del:
                placeholders = ",".join("?" * len(ids_to_del))
                sqlite_conn.execute(
                    f"DELETE FROM graph_edges_v12 WHERE id IN ({placeholders})",
                    ids_to_del,
                )
                sqlite_conn.commit()
                fixed_count += len(ids_to_del)

    # 2. Dangling target edges (target_id FK points to deleted node)
    dangling_tgt_count = sqlite_conn.execute(
        """
        SELECT COUNT(*) FROM graph_edges_v12 e
        LEFT JOIN graph_nodes nt ON nt.id = e.target_id
        WHERE nt.id IS NULL
        """
    ).fetchone()[0]
    if dangling_tgt_count:
        dangling_tgt_rows = sqlite_conn.execute(
            """
            SELECT e.id, ns.uid, nt.uid
            FROM graph_edges_v12 e
            LEFT JOIN graph_nodes ns ON ns.id = e.source_id
            LEFT JOIN graph_nodes nt ON nt.id = e.target_id
            WHERE nt.id IS NULL
            LIMIT 5
            """
        ).fetchall()
        issues.append(
            {
                "category": "dangling_target",
                "count": dangling_tgt_count,
                "sample": [
                    {"edge_id": r[0], "source_uid": r[1], "target_uid": r[2]}
                    for r in dangling_tgt_rows
                ],
            }
        )
        if fix:
            all_dangling_tgt = sqlite_conn.execute(
                """
                SELECT e.id FROM graph_edges_v12 e
                LEFT JOIN graph_nodes nt ON nt.id = e.target_id
                WHERE nt.id IS NULL
                """
            ).fetchall()
            ids_to_del = [r[0] for r in all_dangling_tgt]
            if ids_to_del:
                placeholders = ",".join("?" * len(ids_to_del))
                sqlite_conn.execute(
                    f"DELETE FROM graph_edges_v12 WHERE id IN ({placeholders})",
                    ids_to_del,
                )
                sqlite_conn.commit()
                fixed_count += len(ids_to_del)

    # 3. Duplicate edges (same source_id/target_id/edge_type/extractor)
    dup_count = sqlite_conn.execute(
        """
        SELECT COUNT(*) FROM (
          SELECT source_id, target_id, edge_type, extractor,
                 COUNT(*) AS cnt
          FROM graph_edges_v12
          GROUP BY source_id, target_id, edge_type, extractor
          HAVING cnt > 1
        )
        """
    ).fetchone()[0]
    if dup_count:
        dup_sample = sqlite_conn.execute(
            """
            SELECT ns.uid, nt.uid, e.edge_type, e.extractor,
                   COUNT(*) AS cnt
            FROM graph_edges_v12 e
            LEFT JOIN graph_nodes ns ON ns.id = e.source_id
            LEFT JOIN graph_nodes nt ON nt.id = e.target_id
            GROUP BY e.source_id, e.target_id, e.edge_type, e.extractor
            HAVING cnt > 1
            ORDER BY cnt DESC
            LIMIT 5
            """
        ).fetchall()
        issues.append(
            {
                "category": "duplicate_edges",
                "count": dup_count,
                "sample": [
                    {
                        "source_uid": r[0],
                        "target_uid": r[1],
                        "edge_type": r[2],
                        "extractor": r[3],
                        "count": r[4],
                    }
                    for r in dup_sample
                ],
            }
        )

    # 3b. W6.10: cross-extractor `contains` duplication. The folder
    # spine is re-emitted by every extractor that touches a file, so
    # the rows differ only by `extractor` and slip past the
    # (…, extractor) check above — yet they inflate degree centrality
    # (which counts COUNT(e.id), not DISTINCT). Collapse to one row
    # per (folder, file) pair.
    contains_dup_rows = sqlite_conn.execute(
        """
        SELECT source_id, target_id, COUNT(*) AS cnt
        FROM graph_edges_v12
        WHERE edge_type='contains'
        GROUP BY source_id, target_id
        HAVING cnt > 1
        """
    ).fetchall()
    contains_extra = sum(int(r[2]) - 1 for r in contains_dup_rows)
    if contains_extra:
        issues.append(
            {
                "category": "duplicate_contains",
                "count": contains_extra,
                "pair_count": len(contains_dup_rows),
            }
        )
        if fix:
            cur = sqlite_conn.execute(
                """
                DELETE FROM graph_edges_v12
                WHERE edge_type='contains' AND id NOT IN (
                  SELECT MIN(id) FROM graph_edges_v12
                  WHERE edge_type='contains'
                  GROUP BY source_id, target_id
                )
                """
            )
            fixed_count += int(cur.rowcount or 0)
            sqlite_conn.commit()

    return issues, fixed_count


def _check_self_loops(sqlite_conn: sqlite3.Connection) -> list[dict[str, Any]]:
    # 5. Self-loop edges (source_id == target_id — extractor bugs)
    self_loop_count = sqlite_conn.execute(
        "SELECT COUNT(*) FROM graph_edges_v12 WHERE source_id = target_id"
    ).fetchone()[0]
    if not self_loop_count:
        return []
    sl_sample = sqlite_conn.execute(
        """
        SELECT ns.uid, e.edge_type FROM graph_edges_v12 e
        LEFT JOIN graph_nodes ns ON ns.id = e.source_id
        WHERE e.source_id = e.target_id LIMIT 5
        """
    ).fetchall()
    return [
        {
            "category": "self_loops",
            "count": self_loop_count,
            "sample": [{"uid": r[0], "edge_type": r[1]} for r in sl_sample],
        }
    ]
