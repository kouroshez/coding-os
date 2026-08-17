"""SQLite connection construction and the per-thread connection pool.

One reason to change: how a connection is opened, tuned, and reused.

Split from `database.py`, which also owns schema versioning and migrations —
those change when the schema changes, these change when concurrency or
throughput does. `database.py` re-exports every name here, so callers keep
importing from it.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Generator
from contextlib import contextmanager, suppress
from pathlib import Path

# Thread-local pool for multi-agent concurrency: one cached connection per
# thread, WAL lets readers run concurrently, and busy_timeout absorbs writer
# contention instead of failing the call.
_thread_local = threading.local()
_pool_lock = threading.Lock()
_pool_stats = {"hits": 0, "misses": 0, "active": 0}

# Ceiling the -wal file is truncated back to. SQLite's default (-1) never gives
# space back, so the file keeps its high-water mark forever — that is how a
# 342 MB database ended up beside a 59 GB WAL holding 531 live frames.
#
# Measured on SQLite 3.50.4: the limit is applied when the WAL *restarts*
# (wraps to frame 0), which is the first write after a completed checkpoint —
# NOT at checkpoint completion. A checkpoint alone leaves the file at its
# high-water size, so probing right after one looks like the pragma is
# ignored. It isn't; the next write does the truncation. An idle-but-pinned
# database never restarts its WAL, which is why the SessionStart guard in
# auto-brain-decay.sh exists as the complement to this cap.
#
# Sits above the ~4 MB wal_autocheckpoint target so normal operation never pays
# for a truncate, and below the 50 MB WAL budget `cos doctor` warns at so a
# healthy WAL never trips that check.
WAL_SIZE_LIMIT_BYTES = 32 * 1024 * 1024


def _default_db_path() -> str:
    # Resolved per call, not bound at import: the path depends on the project
    # root, and a module-level snapshot would pin the first one ever seen.
    try:
        from .database import DEFAULT_DB_PATH
    except ImportError:
        from database import DEFAULT_DB_PATH  # type: ignore[no-redef]

    return str(DEFAULT_DB_PATH)


def apply_pragmas(conn: sqlite3.Connection) -> None:
    """Apply performance and safety PRAGMAs.

    Tuned for consumer repos up to ~10x meta-repo size (~400K graph nodes,
    ~600MB DB). Trade-off chosen: durability >= NORMAL (WAL still crash-safe),
    throughput maximized via mmap + large cache.
    """
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")  # 3-5x faster writes; WAL still crash-safe
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA temp_store = MEMORY")  # sort/group spill to RAM, not disk
    conn.execute("PRAGMA cache_size = -65536")  # 64 MB page cache (signed = KB)
    conn.execute("PRAGMA mmap_size = 268435456")  # 256 MB memory-mapped I/O — skips read() syscalls
    conn.execute("PRAGMA wal_autocheckpoint = 1000")  # checkpoint every ~4MB of WAL (4KB pages)
    conn.execute(f"PRAGMA journal_size_limit = {WAL_SIZE_LIMIT_BYTES}")  # see the constant
    conn.execute("PRAGMA busy_timeout = 5000")  # 5s wait on locked DB instead of immediate fail


def _open(path: str) -> sqlite3.Connection:
    # check_same_thread=False: the single-writer model is enforced by
    # SqliteBackend's RLock + WAL. Without it, any consumer sharing the
    # connection across threads (MCP server, web routes, test harness) hits
    # sqlite3.ProgrammingError.
    conn = sqlite3.connect(path, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    apply_pragmas(conn)
    return conn


def get_connection(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Open a connection with WAL mode and safety PRAGMAs."""
    return _open(str(db_path or _default_db_path()))


def get_pooled_conn(db_path: str | Path | None = None) -> sqlite3.Connection:
    path = str(db_path or _default_db_path())
    existing = getattr(_thread_local, "conns", {}).get(path)
    if existing is not None:
        try:
            existing.execute("SELECT 1").fetchone()
            with _pool_lock:
                _pool_stats["hits"] += 1
            return existing
        except sqlite3.Error:
            pass  # Dead connection, reopen below

    conn = _open(path)
    if not hasattr(_thread_local, "conns"):
        _thread_local.conns = {}
    _thread_local.conns[path] = conn
    with _pool_lock:
        _pool_stats["misses"] += 1
        _pool_stats["active"] += 1
    return conn


def close_pool() -> None:
    """Close all pooled connections for the current thread. Safe to call repeatedly."""
    conns = getattr(_thread_local, "conns", {})
    for conn in conns.values():
        with suppress(sqlite3.Error):
            conn.close()
    _thread_local.conns = {}
    with _pool_lock:
        _pool_stats["active"] = max(0, _pool_stats["active"] - len(conns))


def pool_stats() -> dict[str, int]:
    """Return pool stats snapshot for observability."""
    with _pool_lock:
        return dict(_pool_stats)


@contextmanager
def db_connection(db_path: str | Path | None = None) -> Generator[sqlite3.Connection, None, None]:
    """Context manager that yields a connection and closes it on exit."""
    conn = get_connection(db_path)
    try:
        yield conn
    finally:
        conn.close()
