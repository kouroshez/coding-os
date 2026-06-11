"""Tests for migration v20 — override audit columns (TASK-107)."""

from __future__ import annotations

import sqlite3

import pytest

from core.thinking_os.database import (
    MIGRATIONS,
    _migrate_v13_board_os,
    _migrate_v20_override_audit,
    get_schema_version,
    has_task_status_history_table,
    run_migrations,
)


@pytest.fixture
def conn() -> sqlite3.Connection:
    """An in-memory DB seeded up to v13 (so task_status_history exists)."""
    c = sqlite3.connect(":memory:")
    # Seed minimum: tasks table from v13 migration.
    c.executescript("""
        CREATE TABLE IF NOT EXISTS tasks (
            task_id TEXT PRIMARY KEY,
            title TEXT,
            status TEXT,
            file_path TEXT,
            agent_session TEXT,
            work_log_last_5 TEXT DEFAULT '[]',
            labels_json TEXT DEFAULT '[]'
        );
    """)
    _migrate_v13_board_os(c)
    return c


def test_v20_adds_override_columns(conn: sqlite3.Connection) -> None:
    assert has_task_status_history_table(conn)
    cols_before = {r[1] for r in conn.execute("PRAGMA table_info(task_status_history)")}
    assert "override_reason" not in cols_before
    assert "override_actor" not in cols_before

    _migrate_v20_override_audit(conn)

    cols_after = {r[1] for r in conn.execute("PRAGMA table_info(task_status_history)")}
    assert "override_reason" in cols_after
    assert "override_actor" in cols_after


def test_v20_is_idempotent(conn: sqlite3.Connection) -> None:
    _migrate_v20_override_audit(conn)
    # Second run must not raise.
    _migrate_v20_override_audit(conn)


def test_v20_creates_partial_index(conn: sqlite3.Connection) -> None:
    _migrate_v20_override_audit(conn)
    indices = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='task_status_history'"
        )
    }
    assert "idx_tsh_override" in indices


def test_v20_existing_rows_backfill_null(conn: sqlite3.Connection) -> None:
    # Insert a row before the migration runs.
    conn.execute(
        """
        INSERT INTO task_status_history
            (task_id, old_status, new_status, agent_session, reason, transitioned_at)
        VALUES ('TASK-001', 'icebox', 'in_progress', 'ses-claude', 'init', 1)
        """
    )
    conn.commit()

    _migrate_v20_override_audit(conn)

    row = conn.execute(
        "SELECT override_reason, override_actor FROM task_status_history WHERE task_id = 'TASK-001'"
    ).fetchone()
    assert row == (None, None)


def test_v20_skips_when_history_table_missing() -> None:
    """Defensive: if task_status_history doesn't exist, the migration logs and exits."""
    fresh = sqlite3.connect(":memory:")
    # Don't run v13 — table is absent.
    _migrate_v20_override_audit(fresh)  # must not raise
    has = has_task_status_history_table(fresh)
    assert has is False  # we genuinely skipped


def test_v20_is_in_migration_chain() -> None:
    """v20 (override audit) is registered in the migration chain.

    No longer asserts last-migration position — later migrations
    followed. Just verifies v20 is still discoverable.
    """
    by_version = {row[0]: row[1] for row in MIGRATIONS}
    assert 20 in by_version, "v20 missing from MIGRATIONS"
    assert "Override audit columns" in by_version[20]


def test_v20_runs_via_run_migrations() -> None:
    """run_migrations applies v20 cleanly on a fresh in-memory DB."""
    db = sqlite3.connect(":memory:")
    run_migrations(db)
    sv = get_schema_version(db)
    assert sv >= 20
    cols = {r[1] for r in db.execute("PRAGMA table_info(task_status_history)")}
    assert "override_reason" in cols
    assert "override_actor" in cols


def test_v20_history_row_with_override_reason_persists() -> None:
    """Audit smoke: insert a history row with override_reason after migration."""
    c = sqlite3.connect(":memory:")
    c.executescript("""
        CREATE TABLE IF NOT EXISTS tasks (
            task_id TEXT PRIMARY KEY,
            title TEXT,
            status TEXT,
            file_path TEXT,
            agent_session TEXT,
            work_log_last_5 TEXT DEFAULT '[]',
            labels_json TEXT DEFAULT '[]'
        );
    """)
    _migrate_v13_board_os(c)
    _migrate_v20_override_audit(c)

    c.execute(
        """
        INSERT INTO task_status_history
            (task_id, old_status, new_status, agent_session, reason,
             transitioned_at, override_reason, override_actor)
        VALUES ('TASK-001', 'in_progress', 'complete', 'ses-claude',
                'task-done', 1, 'Hotfix INC-42; verify ran locally', 'claude')
        """
    )
    c.commit()
    row = c.execute(
        "SELECT override_reason, override_actor FROM task_status_history WHERE task_id = 'TASK-001'"
    ).fetchone()
    assert row[0].startswith("Hotfix")
    assert row[1] == "claude"
