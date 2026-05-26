"""graph_os — SQLite fallback backend.

DEPENDS:  sqlite3 stdlib; core/thinking_os/database.py for init_db when
          path-based; core/graph_os/types.py for the value types.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from ..types import EvidenceSignal, GraphEdge, GraphNode, normalize_kind

logger = logging.getLogger("graph_os.backends.sqlite")


def _import_db_module() -> Any:
    """Return the thinking_os database module.

    Prefers the installed package path (`thinking_os.database`); falls back
    to the bare ``database`` name for environments where
    core/thinking_os/ is on sys.path directly (e.g. direct script
    invocation without editable install).
    """
    try:
        from thinking_os import database as _db  # type: ignore

        return _db
    except ImportError:
        import database as _db  # type: ignore

        return _db


class SqliteBackend:
    """SQLite-backed graph store (thinking_os DB, migration v12).

    DEPENDS:  migration v12 (graph_nodes, graph_edges_v12,
              graph_evidence_v12 tables + optional FTS5 virtual
              table).
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
        # P6: per-thread read connections. WAL allows multiple concurrent
        # readers; a single shared sqlite3.Connection serialises them
        # behind the GIL + connection mutex. Opening one connection per
        # thread (lazy) unblocks true parallel reads in Hub UI + parallel
        # MCP dispatch. Track all opened conns so close() can drain them.
        self._db_path: str | None = None
        self._read_conn_pool = threading.local()
        self._all_read_conns: list[sqlite3.Connection] = []
        self._read_conn_lock = threading.Lock()
        if conn is not None:
            self._conn = conn
        else:
            try:
                from thinking_os.database import resolve_db_path  # type: ignore

                resolved = db_path or str(resolve_db_path())
            except ImportError:
                # Standalone — fall back to env var + repo-relative default.
                resolved = db_path or os.environ.get("COS_DB_PATH", ".coding-os/coding-os.db")
            Path(resolved).parent.mkdir(parents=True, exist_ok=True)
            db = _import_db_module()
            # B1: own-connection path opens with check_same_thread=False so
            # multiple MCP threads can share this backend instance. WAL +
            # busy_timeout give us concurrent readers + a writer without
            # SQLITE_BUSY spam.
            self._db_path = resolved
            self._conn = sqlite3.connect(resolved, timeout=10, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode = WAL")
            self._conn.execute("PRAGMA synchronous = NORMAL")
            self._conn.execute("PRAGMA foreign_keys = ON")
            # 30s ceiling tolerates ten concurrent dispatcher workers
            # reindexing different files at the same time without the
            # busy_timeout firing.
            self._conn.execute("PRAGMA busy_timeout = 30000")
            # G16: apply the full pragma SSOT (cache_size, mmap_size,
            # temp_store, wal_autocheckpoint) so standalone-conn bench
            # harnesses (bench/scale_500k.py, bench/viewer_fps.py) +
            # reindex_dispatch.py see the same p99 SLA the pooled path
            # does. Fail-open if helper unavailable (older DB module).
            _apply_pragmas = getattr(db, "_apply_pragmas", None)
            if callable(_apply_pragmas):
                try:
                    _apply_pragmas(self._conn)
                except Exception as exc:  # pragma: no cover — diagnostic
                    logger.debug("standalone PRAGMA application skipped: %s", exc)
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
        # P6: drain per-thread read connections too.
        with self._read_conn_lock:
            for conn in self._all_read_conns:
                try:
                    conn.close()
                except sqlite3.Error as exc:
                    logger.debug("sqlite read-conn close suppressed: %s", exc)
            self._all_read_conns.clear()

    def _get_read_conn(self) -> sqlite3.Connection:
        """P6: return this thread's read-only sqlite3.Connection.

        Lazy-open per thread under WAL so concurrent get_node /
        count_edges / list_edges calls don't serialise behind the
        primary connection's GIL+mutex. Falls back to the shared
        connection when ``_db_path`` is unset (caller-provided conn
        via constructor) — tests + caller-pooled scenarios keep
        working unchanged.
        """
        if self._db_path is None:
            return self._conn
        conn = getattr(self._read_conn_pool, "conn", None)
        if conn is not None:
            return conn
        conn = sqlite3.connect(
            self._db_path, timeout=10, check_same_thread=False
        )
        conn.row_factory = sqlite3.Row
        # Read connections need WAL so they see committed writes
        # immediately. Foreign keys + query_only enforce read-only
        # semantics (defence-in-depth). Cache stays modest (~2MB
        # default) so 16 threads don't multiply the 64MB primary cache.
        try:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA query_only = ON")
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA busy_timeout = 30000")
        except sqlite3.Error as exc:
            logger.debug("read-conn pragma skipped: %s", exc)
        self._read_conn_pool.conn = conn
        with self._read_conn_lock:
            self._all_read_conns.append(conn)
        return conn

    # -- Write path --------------------------------------------------------

    def upsert_node(self, node: GraphNode) -> int:
        """Insert a node or update it in place; return the primary key.

        DEPENDS:  migration v12 schema.
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
                "SELECT id, doc_blob, signature, metadata_json FROM graph_nodes WHERE uid = ?",
                (node.uid,),
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
            existing_doc_blob = row[1]
            existing_signature = row[2]
            existing_meta_json = row[3]
            incoming_is_stub = bool(node.metadata.get("stub")) if node.metadata else False
            existing_meta = json.loads(existing_meta_json or "{}")
            existing_is_stub = bool(existing_meta.get("stub"))

            doc_blob_to_write = node.doc_blob
            sig_to_write = node.signature
            meta_to_write = metadata_json
            if incoming_is_stub and not existing_is_stub:
                doc_blob_to_write = existing_doc_blob
                sig_to_write = existing_signature
                meta_to_write = existing_meta_json or metadata_json
            else:
                if existing_doc_blob and not node.doc_blob:
                    doc_blob_to_write = existing_doc_blob
                if existing_signature and not node.signature:
                    sig_to_write = existing_signature

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
                    sig_to_write,
                    node.lang,
                    doc_blob_to_write,
                    node.ast_hash,
                    node.content_hash,
                    meta_to_write,
                    now,
                    node_id,
                ),
            )
            self._conn.commit()
            return node_id

    def upsert_edge(self, edge: GraphEdge) -> int:
        """Insert or update an edge; replace evidence atomically.

        DEPENDS:  upsert_node must have been called for both endpoints.

        F12 / Audit #3: extractors occasionally emit self-loops
        (source_uid == target_uid) when an AST visitor mis-resolves
        recursion or nested attribute access. They poison call-graph
        analytics. Drop them at the backend write boundary so a single
        fix covers every extractor.
        """
        if edge.source_uid == edge.target_uid:
            logger.debug("self-loop dropped at upsert_edge: uid=%s type=%s", edge.source_uid, edge.edge_type)
            return -1
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
                    cursor.execute("DELETE FROM graph_evidence_v12 WHERE edge_id=?", (edge_id,))

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
            if self.upsert_edge(edge) >= 0:
                edge_count += 1
        return node_count, edge_count

    def delete_node(self, uid: str) -> bool:
        """Remove a node; FK CASCADE removes edges + evidence."""
        with self._write_lock:
            cursor = self._conn.execute("DELETE FROM graph_nodes WHERE uid=?", (uid,))
            self._conn.commit()
            return cursor.rowcount > 0

    def delete_nodes_for_file(
        self, file_path: str, *, extractors: Sequence[str] | None = None
    ) -> int:
        """Prune nodes belonging to a single source file before reindex."""
        with self._write_lock:
            if not extractors:
                cursor = self._conn.execute(
                    "DELETE FROM graph_nodes WHERE file_path=?", (file_path,)
                )
                self._conn.commit()
                return int(cursor.rowcount or 0)
            placeholders = " OR ".join(["metadata_json LIKE ?"] * len(extractors))
            params: list[Any] = [file_path]
            for ex in extractors:
                params.append(f'%"extractor": "{ex}"%')
            cursor = self._conn.execute(
                f"DELETE FROM graph_nodes WHERE file_path=? AND ({placeholders})",
                params,
            )
            self._conn.commit()
            return int(cursor.rowcount or 0)

    def link_external_stubs(self, *, file_path: str | None = None) -> int:
        with self._write_lock:
            if file_path:
                stub_rows = self._conn.execute(
                    """
                    SELECT DISTINCT stub.id, stub.uid
                    FROM graph_edges_v12 e
                    JOIN graph_nodes stub ON stub.id = e.target_id
                    JOIN graph_nodes src ON src.id = e.source_id
                    WHERE src.file_path = ?
                      AND stub.uid LIKE 'code:external:%'
                      AND stub.uid NOT LIKE 'code:external:unresolved:%'
                    """,
                    (file_path,),
                ).fetchall()
            else:
                stub_rows = self._conn.execute(
                    """
                    SELECT id, uid FROM graph_nodes
                    WHERE uid LIKE 'code:external:%'
                      AND uid NOT LIKE 'code:external:unresolved:%'
                    """
                ).fetchall()

            stubs_by_label: dict[str, list[tuple[int, str, str]]] = {}
            for stub_id, stub_uid in stub_rows:
                rest = stub_uid[len("code:external:") :]
                module, _, name = rest.rpartition(":")
                if not module or not name:
                    continue
                stubs_by_label.setdefault(name, []).append((int(stub_id), module, stub_uid))

            if not stubs_by_label:
                return 0

            labels = list(stubs_by_label.keys())
            placeholders = ",".join(["?"] * len(labels))
            real_rows = self._conn.execute(
                f"""
                SELECT id, label, file_path FROM graph_nodes
                WHERE kind IN ('function','method','class','variable','interface')
                  AND label IN ({placeholders})
                  AND file_path IS NOT NULL
                """,
                tuple(labels),
            ).fetchall()
            real_by_label: dict[str, list[tuple[int, str]]] = {}
            for real_id, real_label, real_file in real_rows:
                real_by_label.setdefault(real_label, []).append((int(real_id), real_file))

            rewrites = 0
            for label, candidate_stubs in stubs_by_label.items():
                real_candidates = real_by_label.get(label, [])
                if not real_candidates:
                    continue
                for stub_id, module, _stub_uid in candidate_stubs:
                    module_suffix = module.replace(".", "/")
                    matched_real_id: int | None = None
                    for real_id, real_file in real_candidates:
                        if (
                            real_file == f"{module_suffix}.py"
                            or real_file.endswith(f"/{module_suffix}.py")
                            or real_file == f"{module_suffix}/__init__.py"
                            or real_file.endswith(f"/{module_suffix}/__init__.py")
                        ):
                            matched_real_id = real_id
                            break
                    if matched_real_id is None:
                        continue
                    self._conn.execute(
                        "UPDATE graph_edges_v12 SET target_id = ? WHERE target_id = ?",
                        (matched_real_id, stub_id),
                    )
                    rewrites += 1
            self._conn.commit()
            return rewrites

    # -- Read path ---------------------------------------------------------

    def get_node(self, uid: str) -> GraphNode | None:
        # G18: pure-SELECT, no write_lock — WAL gives concurrent
        # readers; the lock here was serialising reads behind any
        # in-flight write for no correctness benefit.
        # P6: thread-local read connection so parallel get_node calls
        # don't serialise behind the primary conn's mutex+GIL.
        row = self._get_read_conn().execute(
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

    def _node_id_for_uid(self, uid: str) -> int:
        row = self._conn.execute("SELECT id FROM graph_nodes WHERE uid=?", (uid,)).fetchone()
        if row is None:
            raise ValueError(f"unknown uid {uid!r}: upsert the node before emitting edges")
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
