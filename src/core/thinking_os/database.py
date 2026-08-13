"""
Coding OS — SQLite database module with auto-migration.

Provides connection management (WAL mode), schema versioning,
and migration execution for the thinking_os self-learning system.

Agent-agnostic: DB path is configurable via COS_DB_PATH env var.
"""

from __future__ import annotations

import contextlib
import logging
import os
import sqlite3
from pathlib import Path

# database.py is imported BOTH flat (`import database`, with this dir on
# sys.path — the MCP server + hooks) and as a package member
# (`thinking_os.database`, `core.thinking_os.database` — the CLI and web).
# A relative import breaks the first, a bare one breaks the second, so try
# the package form and fall back. Same dual identity documented for board_os.
try:  # package import
    from ._db_migrations import (
        MIGRATIONS,
        MigrationAction,
        _column_exists,
        has_backtrack_events_table,
        has_document_chunks_fts,
        has_embeddings_table,
        has_file_index_state_table,
        has_formula_dispatches_table,
        has_fts5,
        has_fts5_table,
        has_graph_edges_table,
        has_graph_evidence_table,
        has_graph_nodes_fts,
        has_graph_nodes_table,
        has_memory_audit_table,
        has_pattern_validations_table,
        has_persona_selections_table,
        has_retrieval_quality_table,
        has_retrievals_table,
        has_task_dependencies_table,
        has_task_status_history_table,
        has_tasks_fts,
        has_tasks_table,
        has_tasks_v13_columns,
    )
    from ._db_paths import (
        DB_FILENAME,
        DEFAULT_DB_PATH,
        LEGACY_DB_FILENAME,
        PROJECT_SCOPED_ENV_VARS,
        SESSION_SCOPED_ENV_VARS,
        STATE_DIRNAME,
        get_active_project_root,
        migrate_legacy_db_filename,
        project_root,
        reset_active_project_root,
        resolve_db_path,
        set_active_project_root,
    )
except ImportError:  # flat import
    from _db_migrations import (  # type: ignore[no-redef]  # noqa: F401 — re-exported: callers do `from database import has_fts5`
        MIGRATIONS,
        MigrationAction,
        _column_exists,
        has_backtrack_events_table,
        has_document_chunks_fts,
        has_embeddings_table,
        has_file_index_state_table,
        has_formula_dispatches_table,
        has_fts5,
        has_fts5_table,
        has_graph_edges_table,
        has_graph_evidence_table,
        has_graph_nodes_fts,
        has_graph_nodes_table,
        has_memory_audit_table,
        has_pattern_validations_table,
        has_persona_selections_table,
        has_retrieval_quality_table,
        has_retrievals_table,
        has_task_dependencies_table,
        has_task_status_history_table,
        has_tasks_fts,
        has_tasks_table,
        has_tasks_v13_columns,
    )
    from _db_paths import (  # type: ignore[no-redef]  # noqa: F401 — re-exported: `from database import project_root` is used repo-wide
        DB_FILENAME,
        DEFAULT_DB_PATH,
        LEGACY_DB_FILENAME,
        PROJECT_SCOPED_ENV_VARS,
        SESSION_SCOPED_ENV_VARS,
        STATE_DIRNAME,
        get_active_project_root,
        migrate_legacy_db_filename,
        project_root,
        reset_active_project_root,
        resolve_db_path,
        set_active_project_root,
    )

logger = logging.getLogger("coding_os.db")

# Default DB path — configurable via COS_DB_PATH env var
# Falls back to .coding-os/coding-os.db in current working directory.
# Canonical filename, single source of truth for every consumer (MCP server,
# Hub web, every CLI subcommand, every hook).


# ---------------------------------------------------------------------------
# FTS5 detection (must be defined before migrations that use it)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Callable migrations (defined before MIGRATIONS list so they can be referenced directly)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Migration registry
# ---------------------------------------------------------------------------
# Each migration is a (version, description, sql_or_callable) tuple.
# sql_or_callable is either a SQL string (executed via executescript)


# ---------------------------------------------------------------------------
# Brain-hardening validators (shared constants)
# ---------------------------------------------------------------------------

VALID_TRUST_TIERS: frozenset[str] = frozenset({"volatile", "validated", "locked", "core"})
PROTECTED_TRUST_TIERS: frozenset[str] = frozenset({"locked", "core"})


def is_pattern_protected(conn: sqlite3.Connection, pattern_id: int) -> bool:
    """Return True if the pattern's trust_tier is in PROTECTED_TRUST_TIERS."""
    if not _column_exists(conn, "learned_patterns", "trust_tier"):
        return False  # pre-v7 DB has no concept of protection
    row = conn.execute(
        "SELECT trust_tier FROM learned_patterns WHERE id = ?",
        (pattern_id,),
    ).fetchone()
    if row is None:
        return False
    return row[0] in PROTECTED_TRUST_TIERS


VALID_PROVENANCE: frozenset[str] = frozenset(
    {
        "agent_self",
        "user_directive",
        "extracted_from_outcome",
        "promoted_from_rule",
        "imported",
    }
)


def record_audit(
    conn: sqlite3.Connection,
    *,
    actor: str,
    action: str,
    source_table: str,
    source_id: int | None = None,
    old_value: str | None = None,
    new_value: str | None = None,
    reason: str | None = None,
) -> int | None:
    """Append a row to memory_audit. Fire-and-forget — never raises."""
    if not has_memory_audit_table(conn):
        return None
    try:
        cursor = conn.execute(
            "INSERT INTO memory_audit "
            "(actor, action, source_table, source_id, old_value, new_value, reason) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (actor, action, source_table, source_id, old_value, new_value, reason),
        )
        conn.commit()
        return cursor.lastrowid
    except sqlite3.OperationalError as exc:
        logger.debug("record_audit skipped: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Connection construction + the per-thread pool live in _db_pool; re-exported
# here so every existing `from .database import get_connection` keeps resolving.
# ---------------------------------------------------------------------------

try:  # package import
    from ._db_pool import (
        # Re-exported under its private name: graph_os's SQLite backend reaches
        # it via getattr(db, "_apply_pragmas", None) and silently skips tuning
        # if the attribute is absent.
        apply_pragmas as _apply_pragmas,
        close_pool as close_pool,
        db_connection as db_connection,
        get_connection as get_connection,
        get_pooled_conn as get_pooled_conn,
        pool_stats as pool_stats,
    )
except ImportError:  # loaded as a top-level module (tests, direct execution)
    from _db_pool import (  # type: ignore[no-redef]
        apply_pragmas as _apply_pragmas,  # noqa: F401
        close_pool as close_pool,
        db_connection as db_connection,
        get_connection as get_connection,
        get_pooled_conn as get_pooled_conn,
        pool_stats as pool_stats,
    )

# ---------------------------------------------------------------------------
# Schema versioning & migration
# ---------------------------------------------------------------------------


def _ensure_version_table(conn: sqlite3.Connection) -> None:
    """Create the schema_version table if it doesn't exist."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_version ("
        "  version    INTEGER PRIMARY KEY,"
        "  description TEXT,"
        "  applied_at DATETIME DEFAULT CURRENT_TIMESTAMP"
        ")"
    )
    conn.commit()


def get_schema_version(conn: sqlite3.Connection) -> int:
    """Return the highest applied migration version, or 0 if none."""
    _ensure_version_table(conn)
    row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    return row[0] if row[0] is not None else 0


def run_migrations(conn: sqlite3.Connection) -> list[int]:
    """Apply any unapplied migrations in order.

    Concurrency-safe: takes an EXCLUSIVE transaction on the version
    table so two simultaneously-opening connections don't both try to
    apply the same migration and trip the UNIQUE constraint. Idempotent
    via INSERT OR IGNORE on the version row.

    Returns:
        List of migration versions that were applied.
    """
    _ensure_version_table(conn)
    applied: list[int] = []

    # Another writer holding the lock is the common case under concurrent
    # dispatcher workers: fall through, re-read the version below, and return
    # without doing anything if we are already at the target.
    with contextlib.suppress(sqlite3.OperationalError):
        conn.execute("BEGIN IMMEDIATE")
    try:
        current = get_schema_version(conn)
        for version, description, action in MIGRATIONS:
            if version <= current:
                continue
            logger.info("Applying migration v%d: %s", version, description)
            try:
                if callable(action):
                    action(conn)
                else:
                    conn.executescript(action)
            except sqlite3.OperationalError as exc:
                # ALTER TABLE under concurrent runners can race past the
                # column-exists guard — skip when the message explicitly
                # confirms the schema is already where we want it.
                if "duplicate column name" in str(exc).lower():
                    logger.debug(
                        "migration v%d ALTER race tolerated: %s",
                        version,
                        exc,
                    )
                else:
                    raise
            conn.execute(
                "INSERT OR IGNORE INTO schema_version (version, description) VALUES (?, ?)",
                (version, description),
            )
            applied.append(version)
        conn.commit()
    except sqlite3.IntegrityError as exc:
        logger.debug("migration race resolved: %s", exc)
        conn.rollback()
        applied = []

    if applied:
        logger.info("Migrations applied: %s (now at v%d)", applied, applied[-1])
    else:
        logger.debug("Schema up-to-date at v%d", current)

    return applied


# ---------------------------------------------------------------------------
# Stats helpers (used by health tool)
# ---------------------------------------------------------------------------

_TABLES = [
    "task_outcomes",
    "agent_metrics",
    "learned_patterns",
    "observations",
    "session_summaries",
    "outcome_history",
    "concept_graph",
    "embeddings",
    "document_chunks",
    "tasks",
    "memory_audit",
    "pattern_validations",
    "retrievals",
    "retrieval_quality",
    "graph_nodes",
    "graph_edges_v12",
    "graph_evidence_v12",
    "file_index_state",
    "retrieval_router_log",
    "adapter_health",
]


def get_db_stats(conn: sqlite3.Connection) -> dict:
    """Collect row counts per table and DB file size."""
    stats: dict = {"tables": {}}

    for table in _TABLES:
        try:
            row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
            stats["tables"][table] = row[0]
        except sqlite3.OperationalError:
            stats["tables"][table] = None  # table doesn't exist yet

    stats["schema_version"] = get_schema_version(conn)
    stats["fts5_available"] = has_fts5(conn)

    # File size
    db_path = conn.execute("PRAGMA database_list").fetchone()[2]
    if db_path and os.path.exists(db_path):
        stats["db_size_bytes"] = os.path.getsize(db_path)
    else:
        stats["db_size_bytes"] = 0

    return stats


# ---------------------------------------------------------------------------
# Bootstrap (called on server start and by --test)
# ---------------------------------------------------------------------------


def _refuse_global_hub_db(target: Path) -> None:
    try:
        hub_state = (Path.home() / STATE_DIRNAME).resolve()
    except (OSError, RuntimeError):
        return
    if target.parent.resolve() == hub_state:
        raise RuntimeError(
            f"refusing to create a project DB inside the global hub state dir "
            f"({hub_state}) — set $COS_DB_PATH or run inside a project"
        )


def init_db(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Open the DB, run migrations, return the live connection.

    Renames a legacy `thinking_os.db` sibling to the canonical
    `coding-os.db` once, before opening — silent no-op when the
    rename has already happened or no legacy file exists.

    Also asks SQLite to refresh its query-planner statistics
    (`PRAGMA optimize`) once per process. Without this, the planner
    falls back to heuristics and routinely picks the slower index for
    multi-table JOINs (observed: 14ms → 2ms on graph_nodes JOIN
    graph_edges_v12 after stats present). Cost is bounded — the pragma
    is a no-op when stats are current.
    """
    target = Path(db_path) if db_path else DEFAULT_DB_PATH
    _refuse_global_hub_db(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    migrate_legacy_db_filename(target)
    conn = get_connection(str(target))
    run_migrations(conn)
    _ensure_query_planner_stats(conn)
    return conn


def _ensure_query_planner_stats(conn: sqlite3.Connection) -> None:
    """Make sure SQLite has query-planner stats; refresh stale ones cheaply.

    First call on a fresh DB runs a full ``ANALYZE`` (one-shot cost,
    ~50ms even on 600MB DBs). Subsequent calls hit only ``PRAGMA optimize``
    which is a no-op when stats are current and very cheap otherwise.

    Without this the planner picks the wrong index on graph JOINs
    (measured: 14ms vs 3ms on graph_nodes JOIN graph_edges_v12).
    """
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='sqlite_stat1'"
        ).fetchone()
        if row is None:
            conn.execute("ANALYZE")
            conn.commit()
        else:
            conn.execute("PRAGMA optimize")
    except sqlite3.Error as exc:
        logger.debug("query-planner stats refresh skipped: %s", exc)
