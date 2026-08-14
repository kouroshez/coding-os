"""``file_index_state`` cache probes, upserts and the per-thread connection cache."""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any

from graph_os.tools._reindex_routing import _DOCS_CHAIN_KEY

logger = logging.getLogger("graph_os.reindex_dispatch")


def _lookup_cache(
    rel_path: str,
    *,
    content_hash: str,
    graph_chain_key: str | None,
    graph_chain_list: list[str] | None,
    docs_in_scope: bool,
    project_root: Path,
    db_path: str | None,
) -> dict[str, dict[str, Any]]:
    """Probe ``file_index_state`` for layers whose hash+chain still match.

    Returns a dict keyed by layer name (``docs`` / ``graph``) carrying a
    pre-shaped skip envelope so the caller can slot it straight into the
    result.  Never raises — a missing DB / table just yields no hits.
    """
    hits: dict[str, dict[str, Any]] = {}
    try:
        conn = _open_conn(project_root=project_root, db_path=db_path)
    except Exception as exc:
        logger.debug("cache lookup: conn open failed: %s", exc)
        return hits
    try:
        if not _has_state_table(conn):
            return hits
        # Graph chain lookup — chain join must match exactly.
        if graph_chain_list:
            chain_key = ",".join(graph_chain_list)
            row = conn.execute(
                "SELECT content_hash, nodes_written, edges_written, "
                "parse_errors_count, last_indexed_at, last_error "
                "FROM file_index_state "
                "WHERE file_path = ? AND extractor_chain = ?",
                (rel_path, chain_key),
            ).fetchone()
            if row and row[0] == content_hash and row[5] is None:
                hits["graph"] = {
                    "status": "skipped",
                    "reason": "unchanged",
                    "cache": "hit",
                    "chain": graph_chain_key or "",
                    "nodes_written": int(row[1]),
                    "edges_written": int(row[2]),
                    "parse_errors_count": int(row[3]),
                    "last_indexed_at": int(row[4]),
                }
        # Docs layer lookup.
        if docs_in_scope:
            row = conn.execute(
                "SELECT content_hash, last_indexed_at, last_error "
                "FROM file_index_state "
                "WHERE file_path = ? AND extractor_chain = ?",
                (rel_path, _DOCS_CHAIN_KEY),
            ).fetchone()
            if row and row[0] == content_hash and row[2] is None:
                hits["docs"] = {
                    "status": "skipped",
                    "reason": "unchanged",
                    "cache": "hit",
                    "last_indexed_at": int(row[1]),
                }
    except Exception as exc:
        logger.debug("cache lookup failed: %s", exc)
    return hits


def _record_state_safe(
    rel_path: str,
    *,
    content_hash: str,
    chain_key: str,
    nodes_written: int,
    edges_written: int,
    parse_errors_count: int,
    last_error: str | None,
    project_root: Path,
    db_path: str | None,
    advance_hash: bool,
    duration_ms: int | None = None,
) -> None:
    """Upsert file_index_state; on failure keep previous hash (retry on next call).

    ``advance_hash=False`` preserves the prior content_hash (when a row
    exists) so a failing extractor doesn't claim the file is cached —
    the next dispatch will retry until it succeeds.
    """
    try:
        conn = _open_conn(project_root=project_root, db_path=db_path)
    except Exception as exc:
        logger.debug("state record: conn open failed: %s", exc)
        return
    try:
        if not _has_state_table(conn):
            return
        effective_hash = content_hash
        if not advance_hash:
            prev = conn.execute(
                "SELECT content_hash FROM file_index_state "
                "WHERE file_path = ? AND extractor_chain = ?",
                (rel_path, chain_key),
            ).fetchone()
            if prev is not None:
                effective_hash = prev[0]
        conn.execute(
            "INSERT OR REPLACE INTO file_index_state "
            "(file_path, content_hash, extractor_chain, nodes_written, "
            " edges_written, parse_errors_count, last_indexed_at, last_error, "
            " duration_ms) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                rel_path,
                effective_hash,
                chain_key,
                int(nodes_written),
                int(edges_written),
                int(parse_errors_count),
                int(time.time()),
                last_error,
                int(duration_ms) if duration_ms is not None else None,
            ),
        )
        # Self-heal stale graph-chain rows: when a file's routing changes
        # (e.g. an audit .md that used to go through task_deps,md_links now
        # routes to plain md_links), the old chain's row lingers with its old
        # parse_errors_count and inflates cos_graph_doctor. On a graph-layer
        # write, drop sibling graph rows for this path (keep the docs:md row,
        # which legitimately coexists).
        if chain_key != _DOCS_CHAIN_KEY:
            conn.execute(
                "DELETE FROM file_index_state WHERE file_path = ? "
                "AND extractor_chain != ? AND extractor_chain != ?",
                (rel_path, chain_key, _DOCS_CHAIN_KEY),
            )
        conn.commit()
    except Exception as exc:
        logger.debug("state record failed for %s: %s", rel_path, exc)


_CONN_LOCAL = threading.local()


def _open_conn(*, project_root: Path, db_path: str | None):
    # Per-thread connection cache. init_db re-runs the whole
    # CREATE-IF-NOT-EXISTS migration ladder — each run takes the SQLite
    # write lock even when a no-op, and dispatch used to open THREE fresh
    # connections per file (cache lookup, graph write, state record). Under
    # `graph-reindex -j N` that thundering herd starves workers past their
    # busy_timeout and the whole walk grinds. One
    # connection per thread per DB removes the churn; callers MUST NOT
    # close what this returns.
    from thinking_os.database import init_db, resolve_db_path  # type: ignore

    effective_db = db_path or str(resolve_db_path(project_root))
    cache = getattr(_CONN_LOCAL, "by_db", None)
    if cache is None:
        cache = {}
        _CONN_LOCAL.by_db = cache
    conn = cache.get(effective_db)
    if conn is not None:
        try:
            conn.execute("SELECT 1")
        except Exception:
            conn = None
    if conn is None:
        conn = init_db(effective_db)
        try:
            # Writers serialize in SQLite — under `-j N` plus the hub/MCP
            # background writers, init_db's 5s default surfaces as
            # "database is locked" drops (70/1843 on a full -j4 walk).
            # A bounded 30s wait turns those into short queues; the CLI
            # lock-streak breaker still catches a lock held forever.
            conn.execute("PRAGMA busy_timeout = 30000")
            # Python's legacy deferred transactions upgrade read→write
            # mid-tx; under concurrent writers that upgrade fails with an
            # IMMEDIATE "database is locked" that IGNORES busy_timeout
            # (SQLITE_BUSY_SNAPSHOT). BEGIN IMMEDIATE from the start makes
            # the lock wait happen at BEGIN, where busy_timeout applies.
            conn.isolation_level = "IMMEDIATE"
        except Exception as exc:
            logger.debug("dispatch conn tuning skipped: %s", exc)
        cache[effective_db] = conn
    return conn


def _has_state_table(conn) -> bool:
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='file_index_state'"
        ).fetchone()
    except Exception:
        return False
    return row is not None
