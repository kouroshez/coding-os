"""graph_os — SQLite backend: connection lifecycle and row primitives.

Leaf of the backend package: owns the write lock, the per-thread read-connection
pool, schema verification, and the two primitives (`_node_id_for_uid`,
`_row_to_node`) every other mixin builds on.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ..types import GraphNode

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


class _SqliteConnectionBase:
    """Connection ownership, pooling and schema guard for the SQLite backend."""

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
        conn = sqlite3.connect(self._db_path, timeout=10, check_same_thread=False)
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
