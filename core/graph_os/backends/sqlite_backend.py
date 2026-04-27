"""graph_os — SQLite fallback backend.

PURPOSE:  Implement the GraphBackend Protocol against the shared
          thinking_os SQLite file (migration v12). This is the
          agnostic fallback that runs everywhere Python runs, and is
          the parity target Kuzu must match (Section 12.6 of the
          plan).
INPUT:    an opened sqlite3.Connection (ideally via init_db so the
          v12 migration has already applied) OR a db_path string.
OUTPUT:   a GraphBackend-compatible object.
DEPENDS:  sqlite3 stdlib; core/thinking_os/db.py for init_db when
          path-based; core/graph_os/types.py for the value types.
NOTES:    Uses its own tiny DB connection pool when path-based so
          MCP-side callers that do not share a connection still see
          WAL-mode isolation. Idempotent upserts implemented via
          INSERT ... ON CONFLICT DO UPDATE.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import sys
import threading
import time
from pathlib import Path
from typing import Any, Iterable, Sequence

from ..types import EvidenceSignal, GraphEdge, GraphNode, normalize_kind

logger = logging.getLogger("graph_os.backends.sqlite")


def _import_db_module() -> Any:
    """Locate the thinking_os db module without hardcoding a sys.path tweak.

    Consumers may call get_backend() from several entry points (MCP
    server, CLI, tests) — the server already puts core/thinking_os on
    sys.path, but tests and CLI paths may not. This helper finds the
    right directory relative to graph_os and imports on demand.
    """
    try:
        import db  # type: ignore  # noqa: PLC0415
        return db
    except ImportError:
        graph_os_dir = Path(__file__).resolve().parent.parent
        thinking_os_dir = graph_os_dir.parent / "thinking_os"
        if thinking_os_dir.exists() and str(thinking_os_dir) not in sys.path:
            sys.path.insert(0, str(thinking_os_dir))
        import db  # type: ignore  # noqa: PLC0415
        return db


class SqliteBackend:
    """SQLite-backed graph store (thinking_os DB, migration v12).

    PURPOSE:  Satisfy GraphBackend with ON CONFLICT upserts and plain
              SQL reads. Latency is higher than Kuzu for graph walks
              but every method is correct and deterministic.
    INPUT:    see __init__.
    OUTPUT:   see GraphBackend Protocol.
    DEPENDS:  migration v12 (graph_nodes, graph_edges_v12,
              graph_evidence_v12 tables + optional FTS5 virtual
              table).
    NOTES:    Manages its own connection when constructed from a path
              so the caller gets WAL + foreign-key enforcement.
    """

    backend_id: str = "sqlite"

    def __init__(
        self,
        *,
        conn: sqlite3.Connection | None = None,
        db_path: str | None = None,
    ) -> None:
        self._owns_conn = False
        # B1: serialise writes across threads so sqlite3.Connection (which
        # is only cursor-safe, not write-safe under concurrent INSERT) does
        # not raise ProgrammingError. Reads fall under the same lock to
        # cover BEGIN/COMMIT boundaries in ``upsert_edge``.
        self._write_lock = threading.RLock()
        if conn is not None:
            self._conn = conn
        else:
            resolved = db_path or os.environ.get(
                "COS_DB_PATH", ".coding-os/thinking_os.db"
            )
            Path(resolved).parent.mkdir(parents=True, exist_ok=True)
            db = _import_db_module()
            # B1: own-connection path opens with check_same_thread=False so
            # multiple MCP threads can share this backend instance. WAL +
            # busy_timeout give us concurrent readers + a writer without
            # SQLITE_BUSY spam.
            self._conn = sqlite3.connect(
                resolved, timeout=10, check_same_thread=False
            )
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode = WAL")
            self._conn.execute("PRAGMA synchronous = NORMAL")
            self._conn.execute("PRAGMA foreign_keys = ON")
            self._conn.execute("PRAGMA busy_timeout = 5000")
            db.run_migrations(self._conn)
            self._owns_conn = True
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._verify_schema()

    def _verify_schema(self) -> None:
        db = _import_db_module()
        missing: list[str] = []
        if not db.has_graph_nodes_table(self._conn):
            missing.append("graph_nodes")
        if not db.has_graph_edges_table(self._conn):
            missing.append("graph_edges_v12")
        if not db.has_graph_evidence_table(self._conn):
            missing.append("graph_evidence_v12")
        if missing:
            raise RuntimeError(
                "SqliteBackend: required tables missing "
                f"({', '.join(missing)}). Run migrations (init_db) first."
            )

    # -- Lifecycle ---------------------------------------------------------

    def close(self) -> None:
        if self._owns_conn:
            with self._write_lock:
                try:
                    self._conn.close()
                except sqlite3.Error as exc:
                    logger.debug("sqlite close suppressed: %s", exc)

    # -- Write path --------------------------------------------------------

    def upsert_node(self, node: GraphNode) -> int:
        """Insert a node or update it in place; return the primary key.

        PURPOSE:  Idempotent write keyed on uid.
        INPUT:    GraphNode.
        OUTPUT:   integer graph_nodes.id.
        DEPENDS:  migration v12 schema.
        NOTES:    metadata is JSON-serialised; unknown keys survive
                  round-trip. updated_at always refreshed.
        """
        now = int(time.time())
        metadata_json = json.dumps(dict(node.metadata), sort_keys=True)
        # Canonicalise kind at the storage boundary (S3 NodeKind). Falls
        # back to the raw string if normalize_kind doesn't recognise the
        # form so a stray label can't kill an entire reindex run.
        try:
            kind_value = normalize_kind(node.kind).value
        except ValueError:
            kind_value = node.kind
        with self._write_lock:
            row = self._conn.execute(
                "SELECT id FROM graph_nodes WHERE uid = ?", (node.uid,)
            ).fetchone()
            if row is None:
                cursor = self._conn.execute(
                    """
                    INSERT INTO graph_nodes
                      (kind, label, uid, file_path, start_line, end_line,
                       signature, lang, doc_blob, ast_hash, content_hash,
                       metadata_json, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        kind_value,
                        node.label,
                        node.uid,
                        node.file_path,
                        node.start_line,
                        node.end_line,
                        node.signature,
                        node.lang,
                        node.doc_blob,
                        node.ast_hash,
                        node.content_hash,
                        metadata_json,
                        now,
                        now,
                    ),
                )
                self._conn.commit()
                return int(cursor.lastrowid)

            node_id = int(row[0])
            self._conn.execute(
                """
                UPDATE graph_nodes SET
                  kind=?, label=?, file_path=?, start_line=?, end_line=?,
                  signature=?, lang=?, doc_blob=?, ast_hash=?, content_hash=?,
                  metadata_json=?, updated_at=?
                WHERE id=?
                """,
                (
                    kind_value,
                    node.label,
                    node.file_path,
                    node.start_line,
                    node.end_line,
                    node.signature,
                    node.lang,
                    node.doc_blob,
                    node.ast_hash,
                    node.content_hash,
                    metadata_json,
                    now,
                    node_id,
                ),
            )
            self._conn.commit()
            return node_id

    def upsert_edge(self, edge: GraphEdge) -> int:
        """Insert or update an edge; replace evidence atomically.

        PURPOSE:  Keep the (source, target, edge_type, extractor)
                  tuple unique across re-resolves and rewrite the
                  evidence trail in a single transaction.
        INPUT:    GraphEdge.
        OUTPUT:   integer graph_edges_v12.id.
        DEPENDS:  upsert_node must have been called for both endpoints.
        NOTES:    Raises ValueError when source/target uid is unknown
                  — edges cannot dangle.
        """
        now = int(time.time())
        with self._write_lock:
            source_id = self._node_id_for_uid(edge.source_uid)
            target_id = self._node_id_for_uid(edge.target_uid)
            cursor = self._conn.cursor()
            try:
                cursor.execute("BEGIN")
                row = cursor.execute(
                    """
                    SELECT id FROM graph_edges_v12
                    WHERE source_id=? AND target_id=? AND edge_type=? AND extractor=?
                    """,
                    (source_id, target_id, edge.edge_type, edge.extractor),
                ).fetchone()
                if row is None:
                    cursor.execute(
                        """
                        INSERT INTO graph_edges_v12
                          (source_id, target_id, edge_type, confidence,
                           extractor, source_span, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            source_id,
                            target_id,
                            edge.edge_type,
                            float(edge.confidence),
                            edge.extractor,
                            edge.source_span,
                            now,
                            now,
                        ),
                    )
                    edge_id = int(cursor.lastrowid)
                else:
                    edge_id = int(row[0])
                    cursor.execute(
                        """
                        UPDATE graph_edges_v12 SET
                          confidence=?, source_span=?, updated_at=?
                        WHERE id=?
                        """,
                        (
                            float(edge.confidence),
                            edge.source_span,
                            now,
                            edge_id,
                        ),
                    )
                    cursor.execute(
                        "DELETE FROM graph_evidence_v12 WHERE edge_id=?", (edge_id,)
                    )

                for signal in edge.evidence:
                    cursor.execute(
                        """
                        INSERT INTO graph_evidence_v12
                          (edge_id, signal_name, weight, note, created_at)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            edge_id,
                            signal.signal_name,
                            float(signal.weight),
                            signal.note,
                            now,
                        ),
                    )
                self._conn.commit()
                return edge_id
            except Exception:
                self._conn.rollback()
                raise

    def bulk_upsert(
        self, nodes: Iterable[GraphNode], edges: Iterable[GraphEdge]
    ) -> tuple[int, int]:
        """Insert many nodes then many edges; return counts written.

        Two-pass so edges never reference an unknown uid.
        """
        node_count = 0
        for node in nodes:
            self.upsert_node(node)
            node_count += 1
        edge_count = 0
        for edge in edges:
            self.upsert_edge(edge)
            edge_count += 1
        return node_count, edge_count

    def delete_node(self, uid: str) -> bool:
        """Remove a node; FK CASCADE removes edges + evidence."""
        with self._write_lock:
            cursor = self._conn.execute(
                "DELETE FROM graph_nodes WHERE uid=?", (uid,)
            )
            self._conn.commit()
            return cursor.rowcount > 0

    # -- Read path ---------------------------------------------------------

    def get_node(self, uid: str) -> GraphNode | None:
        with self._write_lock:
            row = self._conn.execute(
                """
                SELECT kind, label, uid, file_path, start_line, end_line,
                       signature, lang, doc_blob, ast_hash, content_hash,
                       metadata_json
                FROM graph_nodes WHERE uid=?
                """,
                (uid,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_node(row)

    def get_nodes_bulk(self, uids: Sequence[str]) -> dict[str, GraphNode]:
        """B6: batch variant of get_node — one SELECT per call, not N.

        PURPOSE:  avoid the N+1 read pattern in ``_walk_bfs`` where every
                  neighbour triggered its own round-trip to SQLite.
        INPUT:    sequence of uids.
        OUTPUT:   {uid: GraphNode} mapping; missing uids are absent.
        """
        if not uids:
            return {}
        uniq = list(dict.fromkeys(uids))
        result: dict[str, GraphNode] = {}
        # SQLite parameter limit is 999; chunk to stay safely under.
        chunk = 500
        with self._write_lock:
            for start in range(0, len(uniq), chunk):
                group = uniq[start : start + chunk]
                placeholders = ",".join("?" for _ in group)
                rows = self._conn.execute(
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
        with self._write_lock:
            if kind is None:
                row = self._conn.execute(
                    "SELECT COUNT(*) FROM graph_nodes"
                ).fetchone()
            else:
                # Accept legacy or canonical form; storage is canonical.
                try:
                    kind_q = normalize_kind(kind).value
                except ValueError:
                    kind_q = kind
                row = self._conn.execute(
                    "SELECT COUNT(*) FROM graph_nodes WHERE kind=?", (kind_q,)
                ).fetchone()
        return int(row[0])

    def count_edges(self, edge_type: str | None = None) -> int:
        with self._write_lock:
            if edge_type is None:
                row = self._conn.execute(
                    "SELECT COUNT(*) FROM graph_edges_v12"
                ).fetchone()
            else:
                row = self._conn.execute(
                    "SELECT COUNT(*) FROM graph_edges_v12 WHERE edge_type=?",
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
            where_parts.append(
                "e.source_id = (SELECT id FROM graph_nodes WHERE uid=?)"
            )
            params.append(source_uid)
        if target_uid is not None:
            where_parts.append(
                "e.target_id = (SELECT id FROM graph_nodes WHERE uid=?)"
            )
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
        with self._write_lock:
            rows = self._conn.execute(query, params).fetchall()

            evidence_by_edge: dict[int, list[sqlite3.Row]] = {}
            if include_evidence and rows:
                ev_rows = self._conn.execute(
                    """
                    SELECT edge_id, signal_name, weight, note
                    FROM graph_evidence_v12
                    WHERE edge_id IN (%s)
                    ORDER BY id ASC
                    """
                    % ",".join(str(int(r[0])) for r in rows)
                ).fetchall()
                for ev in ev_rows:
                    evidence_by_edge.setdefault(int(ev[0]), []).append(ev)

        edges: list[GraphEdge] = []
        for edge_row in rows:
            evidence_tuple: tuple[EvidenceSignal, ...] = ()
            if include_evidence:
                ev_rows = evidence_by_edge.get(int(edge_row[0]), [])
                evidence_tuple = tuple(
                    EvidenceSignal(
                        signal_name=r[1], weight=float(r[2]), note=r[3]
                    )
                    for r in ev_rows
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
        """B13: return up to `limit` nodes, optionally filtered by kind.

        PURPOSE:  Provide an unbiased node sample for ``cos_graph_similar``.
        INPUT:    kind — filter by node kind, or None for all.
                  limit — max nodes to return.
        OUTPUT:   list of GraphNode ordered by rowid ASC.
        """
        with self._write_lock:
            if kind is None:
                rows = self._conn.execute(
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
                rows = self._conn.execute(
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

    def _node_id_for_uid(self, uid: str) -> int:
        row = self._conn.execute(
            "SELECT id FROM graph_nodes WHERE uid=?", (uid,)
        ).fetchone()
        if row is None:
            raise ValueError(
                f"unknown uid {uid!r}: upsert the node before emitting edges"
            )
        return int(row[0])

    @staticmethod
    def _row_to_node(row: Sequence[Any]) -> GraphNode:
        metadata = {}
        metadata_json = row[11]
        if metadata_json:
            try:
                metadata = json.loads(metadata_json)
            except json.JSONDecodeError as exc:
                logger.debug("metadata JSON decode failed for uid=%s: %s", row[2], exc)
        return GraphNode(
            kind=row[0],
            label=row[1],
            uid=row[2],
            file_path=row[3],
            start_line=row[4],
            end_line=row[5],
            signature=row[6],
            lang=row[7],
            doc_blob=row[8],
            ast_hash=row[9],
            content_hash=row[10],
            metadata=metadata,
        )


__all__ = ["SqliteBackend"]
