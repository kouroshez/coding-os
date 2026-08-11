"""graph_os — SQLite backend: the read path.

Node and edge lookups, counts, samples and the two bulk traversals the export
and impact tools lean on. Every method here uses the per-thread read connection.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterable, Sequence
from typing import Any

from ..types import EvidenceSignal, GraphEdge, GraphNode, normalize_kind
from ._sqlite_connection import _SqliteConnectionBase

logger = logging.getLogger("graph_os.backends.sqlite")


class _SqliteReadMixin(_SqliteConnectionBase):
    """Lookups, counts and bulk traversals."""

    def edges_among(
        self,
        uids: Sequence[str],
        *,
        edge_types: Sequence[str] | None = None,
        exclude_edge_types: Sequence[str] = ("contains",),
        limit: int = 100_000,
    ) -> list[GraphEdge]:
        """Edges whose BOTH endpoints are inside ``uids`` — the semantic
        overlay of a subtree-scoped export (TASK-406). Chunked source-side
        IN query + in-memory target filter."""
        if not uids:
            return []
        chunk = 500
        id_to_uid: dict[int, str] = {}
        uid_list = list(dict.fromkeys(uids))
        for start in range(0, len(uid_list), chunk):
            batch = uid_list[start : start + chunk]
            for row_id, row_uid in self._conn.execute(
                f"SELECT id, uid FROM graph_nodes WHERE uid IN ({','.join('?' * len(batch))})",
                batch,
            ).fetchall():
                id_to_uid[int(row_id)] = str(row_uid)
        member_ids = list(id_to_uid)
        member_set = set(member_ids)
        excluded_types = set(exclude_edge_types or ())
        wanted_types = set(edge_types) if edge_types else None
        edges: list[GraphEdge] = []
        for start in range(0, len(member_ids), chunk):
            batch = member_ids[start : start + chunk]
            rows = self._conn.execute(
                "SELECT source_id, target_id, edge_type, extractor, confidence "
                f"FROM graph_edges_v12 WHERE source_id IN ({','.join('?' * len(batch))})",
                batch,
            ).fetchall()
            for src, tgt, edge_type, extractor, confidence in rows:
                if int(tgt) not in member_set:
                    continue
                if edge_type in excluded_types:
                    continue
                if wanted_types is not None and edge_type not in wanted_types:
                    continue
                edges.append(
                    GraphEdge(
                        source_uid=id_to_uid[int(src)],
                        target_uid=id_to_uid[int(tgt)],
                        edge_type=str(edge_type),
                        extractor=str(extractor or ""),
                        confidence=float(confidence or 0.0),
                    )
                )
                if len(edges) >= limit:
                    return edges
        return edges

    def contains_ancestors_bulk(
        self, uids: Sequence[str]
    ) -> tuple[list[GraphNode], list[GraphEdge]]:
        """Ancestor closure over ``contains`` for a uid SET — one query per
        tree level instead of one walk per node (TASK-403: the per-node
        loop cost ~12 s on a 30k-uid spine export).
        """
        if not uids:
            return [], []
        chunk = 500
        id_to_uid: dict[int, str] = {}

        def _map_ids(ids: Iterable[int]) -> None:
            pending = [i for i in ids if i not in id_to_uid]
            for start in range(0, len(pending), chunk):
                batch = pending[start : start + chunk]
                for row_id, row_uid in self._conn.execute(
                    f"SELECT id, uid FROM graph_nodes WHERE id IN ({','.join('?' * len(batch))})",
                    batch,
                ).fetchall():
                    id_to_uid[int(row_id)] = str(row_uid)

        frontier: set[int] = set()
        uid_list = list(dict.fromkeys(uids))
        for start in range(0, len(uid_list), chunk):
            batch = uid_list[start : start + chunk]
            for row_id, row_uid in self._conn.execute(
                f"SELECT id, uid FROM graph_nodes WHERE uid IN ({','.join('?' * len(batch))})",
                batch,
            ).fetchall():
                id_to_uid[int(row_id)] = str(row_uid)
                frontier.add(int(row_id))

        seen: set[int] = set(frontier)
        new_ids: set[int] = set()
        edge_rows: list[tuple[int, int, float]] = []
        for _ in range(32):  # spine depth ceiling — real trees are ≤ ~12
            if not frontier:
                break
            level_parents: set[int] = set()
            frontier_list = list(frontier)
            for start in range(0, len(frontier_list), chunk):
                batch = frontier_list[start : start + chunk]
                for src, tgt, conf in self._conn.execute(
                    "SELECT source_id, target_id, confidence FROM graph_edges_v12 "
                    f"WHERE edge_type='contains' AND target_id IN ({','.join('?' * len(batch))})",
                    batch,
                ).fetchall():
                    edge_rows.append((int(src), int(tgt), float(conf or 1.0)))
                    if int(src) not in seen:
                        level_parents.add(int(src))
            seen |= level_parents
            new_ids |= level_parents
            frontier = level_parents

        ancestor_nodes: list[GraphNode] = []
        if new_ids:
            _map_ids(new_ids)
            hydrated = self.get_nodes_bulk([id_to_uid[i] for i in new_ids if i in id_to_uid])
            ancestor_nodes = list(hydrated.values())
        spine_edges = [
            GraphEdge(
                source_uid=id_to_uid[src],
                target_uid=id_to_uid[tgt],
                edge_type="contains",
                extractor="spine_closure",
                confidence=conf,
            )
            for src, tgt, conf in edge_rows
            if src in id_to_uid and tgt in id_to_uid
        ]
        return ancestor_nodes, spine_edges

    def get_node(self, uid: str) -> GraphNode | None:
        # G18: pure-SELECT, no write_lock — WAL gives concurrent
        # readers; the lock here was serialising reads behind any
        # in-flight write for no correctness benefit.
        # P6: thread-local read connection so parallel get_node calls
        # don't serialise behind the primary conn's mutex+GIL.
        row = (
            self._get_read_conn()
            .execute(
                """
            SELECT kind, label, uid, file_path, start_line, end_line,
                   signature, lang, doc_blob, ast_hash, content_hash,
                   metadata_json
            FROM graph_nodes WHERE uid=?
            """,
                (uid,),
            )
            .fetchone()
        )
        if row is None:
            return None
        return self._row_to_node(row)

    def get_nodes_bulk(self, uids: Sequence[str]) -> dict[str, GraphNode]:
        """B6: batch variant of get_node — one SELECT per call, not N."""
        if not uids:
            return {}
        uniq = list(dict.fromkeys(uids))
        result: dict[str, GraphNode] = {}
        # SQLite parameter limit is 999; chunk to stay safely under.
        chunk = 500
        # G18: pure-SELECT, no write_lock. P6: thread-local read conn.
        read_conn = self._get_read_conn()
        for start in range(0, len(uniq), chunk):
            group = uniq[start : start + chunk]
            placeholders = ",".join("?" for _ in group)
            rows = read_conn.execute(
                f"""
                SELECT kind, label, uid, file_path, start_line, end_line,
                       signature, lang, doc_blob, ast_hash, content_hash,
                       metadata_json
                FROM graph_nodes WHERE uid IN ({placeholders})
                """,
                tuple(group),
            ).fetchall()
            for row in rows:
                node = self._row_to_node(row)
                result[node.uid] = node
        return result

    def count_nodes(self, kind: str | None = None) -> int:
        # G18: pure-SELECT, no write_lock. P6: thread-local read conn.
        read_conn = self._get_read_conn()
        if kind is None:
            row = read_conn.execute("SELECT COUNT(*) FROM graph_nodes").fetchone()
        else:
            # Accept legacy or canonical form; storage is canonical.
            try:
                kind_q = normalize_kind(kind).value
            except ValueError:
                kind_q = kind
            row = read_conn.execute(
                "SELECT COUNT(*) FROM graph_nodes WHERE kind=?", (kind_q,)
            ).fetchone()
        return int(row[0])

    def count_edges(self, edge_type: str | None = None) -> int:
        # G17: count DISTINCT logical edges (source, target, edge_type).
        # `list_edges` dedupes via highest-confidence subquery — match
        # that semantic here. G18: no write_lock. P6: thread-local conn.
        read_conn = self._get_read_conn()
        if edge_type is None:
            row = read_conn.execute(
                "SELECT COUNT(*) FROM (SELECT DISTINCT source_id, target_id, edge_type FROM graph_edges_v12)"
            ).fetchone()
        else:
            row = read_conn.execute(
                "SELECT COUNT(*) FROM (SELECT DISTINCT source_id, target_id, edge_type FROM graph_edges_v12 WHERE edge_type=?)",
                (edge_type,),
            ).fetchone()
        return int(row[0])

    def list_edges(
        self,
        *,
        source_uid: str | None = None,
        target_uid: str | None = None,
        edge_types: Sequence[str] | None = None,
        confidence_min: float = 0.0,
        include_evidence: bool = False,
        limit: int = 100,
    ) -> list[GraphEdge]:
        """List edges matching filters, ordered by confidence DESC, id ASC.

        Ordering on id ASC as a tie-break makes results deterministic
        — required for parity testing (Section 12.6 of the plan).
        """
        where_parts = ["e.confidence >= ?"]
        params: list[Any] = [float(confidence_min)]

        if source_uid is not None:
            where_parts.append("e.source_id = (SELECT id FROM graph_nodes WHERE uid=?)")
            params.append(source_uid)
        if target_uid is not None:
            where_parts.append("e.target_id = (SELECT id FROM graph_nodes WHERE uid=?)")
            params.append(target_uid)
        if edge_types:
            placeholders = ",".join("?" for _ in edge_types)
            where_parts.append(f"e.edge_type IN ({placeholders})")
            params.extend(edge_types)

        where_sql = " AND ".join(where_parts)
        # Dedupe across extractors: when multiple extractors emit the
        # same logical edge (source, target, edge_type), keep the
        # highest-confidence row (ties broken by lowest id) so the API
        # surface presents one row per relationship instead of N copies.
        query = f"""
            SELECT e.id, ns.uid, nt.uid, e.edge_type, e.extractor,
                   e.confidence, e.source_span
            FROM graph_edges_v12 e
            JOIN graph_nodes ns ON ns.id = e.source_id
            JOIN graph_nodes nt ON nt.id = e.target_id
            WHERE {where_sql}
              AND e.id = (
                SELECT id FROM graph_edges_v12 ee
                WHERE ee.source_id = e.source_id
                  AND ee.target_id = e.target_id
                  AND ee.edge_type = e.edge_type
                ORDER BY ee.confidence DESC, ee.id ASC
                LIMIT 1
              )
            ORDER BY e.confidence DESC, e.id ASC
            LIMIT ?
        """
        params.append(int(limit))
        # G18: pure-SELECT, no write_lock. P6: thread-local read conn.
        read_conn = self._get_read_conn()
        rows = read_conn.execute(query, params).fetchall()

        evidence_by_edge: dict[int, list[sqlite3.Row]] = {}
        if include_evidence and rows:
            ev_rows = read_conn.execute(
                """
                SELECT edge_id, signal_name, weight, note
                FROM graph_evidence_v12
                WHERE edge_id IN ({})
                ORDER BY id ASC
                """.format(",".join(str(int(r[0])) for r in rows))
            ).fetchall()
            for ev in ev_rows:
                evidence_by_edge.setdefault(int(ev[0]), []).append(ev)

        edges: list[GraphEdge] = []
        for edge_row in rows:
            evidence_tuple: tuple[EvidenceSignal, ...] = ()
            if include_evidence:
                ev_rows = evidence_by_edge.get(int(edge_row[0]), [])
                evidence_tuple = tuple(
                    EvidenceSignal(signal_name=r[1], weight=float(r[2]), note=r[3]) for r in ev_rows
                )
            edges.append(
                GraphEdge(
                    source_uid=edge_row[1],
                    target_uid=edge_row[2],
                    edge_type=edge_row[3],
                    extractor=edge_row[4],
                    confidence=float(edge_row[5]),
                    source_span=edge_row[6],
                    evidence=evidence_tuple,
                )
            )
        return edges

    def sample_nodes(self, kind: str | None, limit: int) -> list[GraphNode]:
        """B13: return up to `limit` nodes, optionally filtered by kind."""
        # G18: pure-SELECT, no write_lock. P6: thread-local read conn.
        read_conn = self._get_read_conn()
        if kind is None:
            rows = read_conn.execute(
                """
                SELECT kind, label, uid, file_path, start_line, end_line,
                       signature, lang, doc_blob, ast_hash, content_hash,
                       metadata_json
                FROM graph_nodes
                ORDER BY id ASC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
        else:
            try:
                kind_q = normalize_kind(kind).value
            except ValueError:
                kind_q = kind
            rows = read_conn.execute(
                """
                SELECT kind, label, uid, file_path, start_line, end_line,
                       signature, lang, doc_blob, ast_hash, content_hash,
                       metadata_json
                FROM graph_nodes
                WHERE kind = ?
                ORDER BY id ASC
                LIMIT ?
                """,
                (kind_q, int(limit)),
            ).fetchall()
        return [self._row_to_node(row) for row in rows]

    # -- Internal helpers --------------------------------------------------
