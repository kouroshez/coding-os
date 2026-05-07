"""Tests for migration v13 (Phase L.0) — board_os schema extensions."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


# Allow import from core/thinking_os/database.py without polluting the global path.
import importlib.util


def _load_db_module():
    spec = importlib.util.spec_from_file_location(
        "_db_under_test",
        Path(__file__).resolve().parents[2] / "thinking_os" / "database.py",
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


db = _load_db_module()


@pytest.fixture
def fresh_conn(tmp_path: Path) -> sqlite3.Connection:
    """A fully migrated SQLite DB through v13."""
    return db.init_db(tmp_path / "coding-os.db")


# ---------------------------------------------------------------------------
# Migration v13 surface
# ---------------------------------------------------------------------------


def test_v13_adds_all_new_tasks_columns(fresh_conn: sqlite3.Connection):
    cols = {
        row[1]
        for row in fresh_conn.execute("PRAGMA table_info(tasks)").fetchall()
    }
    expected_new = {
        "swimlane",
        "kind",
        "epic",
        "labels_json",
        "priority",
        "appetite",
        "started_at",
        "completed_at",
        "agent_session",
        "work_log_last_5",
    }
    missing = expected_new - cols
    assert not missing, f"Missing v13 columns on tasks: {missing}"


def test_v13_creates_task_status_history_table(fresh_conn: sqlite3.Connection):
    assert db.has_task_status_history_table(fresh_conn)


def test_v13_status_history_schema(fresh_conn: sqlite3.Connection):
    cols = {
        row[1]: row[2]  # column name → type
        for row in fresh_conn.execute(
            "PRAGMA table_info(task_status_history)"
        ).fetchall()
    }
    assert cols.get("task_id") == "TEXT"
    assert cols.get("old_status") == "TEXT"
    assert cols.get("new_status") == "TEXT"
    assert cols.get("agent_session") == "TEXT"
    assert cols.get("reason") == "TEXT"
    assert cols.get("transitioned_at") == "INTEGER"


def test_v13_indices_created(fresh_conn: sqlite3.Connection):
    indices = {
        row[0]
        for row in fresh_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
    }
    expected = {
        "idx_tsh_task",
        "idx_tsh_session",
        "idx_tasks_swimlane_status",
        "idx_tasks_kind_status",
        "idx_tasks_epic",
        "idx_tasks_priority_status",
    }
    assert expected.issubset(indices), f"Missing indices: {expected - indices}"


def test_v13_helpers_report_present(fresh_conn: sqlite3.Connection):
    assert db.has_tasks_v13_columns(fresh_conn) is True
    assert db.has_task_status_history_table(fresh_conn) is True


# ---------------------------------------------------------------------------
# Idempotence — running v13 twice is a no-op
# ---------------------------------------------------------------------------


def test_v13_is_idempotent(fresh_conn: sqlite3.Connection):
    """Re-running the migration must not error or duplicate columns."""
    db._migrate_v13_board_os(fresh_conn)
    db._migrate_v13_board_os(fresh_conn)  # second time
    # Still exactly one column per name
    col_counts: dict[str, int] = {}
    for row in fresh_conn.execute("PRAGMA table_info(tasks)").fetchall():
        col_counts[row[1]] = col_counts.get(row[1], 0) + 1
    duplicates = {k: v for k, v in col_counts.items() if v > 1}
    assert not duplicates


# ---------------------------------------------------------------------------
# Append-only (Rule 10): pre-v12 tables / columns survived
# ---------------------------------------------------------------------------


def test_v13_does_not_drop_existing_tables(fresh_conn: sqlite3.Connection):
    tables = {
        row[0]
        for row in fresh_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    # Pre-v13 tables that MUST still exist
    pre_v13 = {
        "observations",       # v1
        "learned_patterns",   # v1
        "tasks",              # v6
        "graph_nodes",        # v12
        "graph_edges_v12",    # v12
    }
    missing = pre_v13 - tables
    assert not missing, f"v13 dropped pre-existing tables: {missing}"


def test_v13_preserves_existing_tasks_rows(tmp_path: Path):
    """Insert a row into tasks at v13, verify legacy + new columns coexist."""
    conn = db.init_db(tmp_path / "coding-os.db")
    conn.execute(
        "INSERT INTO tasks (task_id, title, status, file_path, content_hash, mtime) "
        "VALUES ('TASK-001', 'Legacy task', 'open', 'docs/tasks/TASK-001.md', 'abc', 0)"
    )
    conn.commit()
    # Re-run v13 (idempotent) and verify the row is still there with all
    # legacy values intact and new columns NULL/default.
    db._migrate_v13_board_os(conn)
    row = conn.execute(
        "SELECT task_id, title, status, swimlane, kind, labels_json "
        "FROM tasks WHERE task_id='TASK-001'"
    ).fetchone()
    assert row is not None
    assert row[0] == "TASK-001"
    assert row[1] == "Legacy task"
    assert row[2] == "open"      # legacy status preserved
    assert row[3] is None         # new column → NULL
    assert row[4] is None         # new column → NULL
    assert row[5] == "[]"         # default for labels_json
