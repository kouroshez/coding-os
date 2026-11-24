"""
Tests for db.py — migration, WAL mode, table creation, FTS5 detection.

TASK-141: Unit tests for the database module.
"""

from __future__ import annotations

import sqlite3

# Adjust path so we can import from parent
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import (
    get_connection,
    init_db,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> Path:
    """Return a temporary database path."""
    return tmp_path / "test.db"


@pytest.fixture
def fresh_conn(tmp_db_path: Path) -> sqlite3.Connection:
    """Return a fresh connection with pragmas applied but no migrations."""
    conn = get_connection(tmp_db_path)
    yield conn
    conn.close()


@pytest.fixture
def migrated_conn(tmp_db_path: Path) -> sqlite3.Connection:
    """Return a connection with all migrations applied."""
    conn = init_db(tmp_db_path)
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# WAL mode and PRAGMAs
# ---------------------------------------------------------------------------


def _seed_task(
    conn: sqlite3.Connection,
    task_id: str,
    *,
    title: str = "t",
    goal: str = "",
    status: str = "icebox",
    swimlane: str = "core",
    priority: str = "P2",
    completed_at: int | None = None,
    dependencies: str | None = None,
) -> None:
    conn.execute(
        "INSERT INTO tasks (task_id, title, status, file_path, content_hash, mtime, "
        "goal_text, swimlane, priority, completed_at, dependencies) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            task_id,
            title,
            status,
            f"docs/tasks/{task_id}.md",
            "hash",
            0,
            goal,
            swimlane,
            priority,
            completed_at,
            dependencies,
        ),
    )


def _plan(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> str:
    rows = conn.execute("EXPLAIN QUERY PLAN " + sql, params).fetchall()
    return " ".join(str(r[3]) for r in rows)


class TestMigrationV35ScaleFoundation:
    def test_indexes_exist(self, migrated_conn: sqlite3.Connection) -> None:
        idx = {
            r[0]
            for r in migrated_conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()
        }
        assert "idx_tasks_status_completed" in idx
        assert "idx_tasks_swimlane_status_priority" in idx
        assert "idx_task_deps_depends_on" in idx
        # v13 history index the audit asked for already exists.
        assert "idx_tsh_task" in idx

    def test_keyset_query_uses_index(self, migrated_conn: sqlite3.Connection) -> None:
        plan = _plan(
            migrated_conn,
            "SELECT task_id FROM tasks WHERE status = ? ORDER BY completed_at DESC LIMIT 10",
            ("complete",),
        )
        assert "idx_tasks_status_completed" in plan, plan

    def test_fts_table_exists_and_matches(self, migrated_conn: sqlite3.Connection) -> None:
        _seed_task(migrated_conn, "TASK-901", title="pagination keyset", goal="board scale")
        hits = migrated_conn.execute(
            "SELECT rowid FROM tasks_fts WHERE tasks_fts MATCH ?", ("keyset",)
        ).fetchall()
        assert len(hits) == 1

    def test_fts_query_uses_virtual_index(self, migrated_conn: sqlite3.Connection) -> None:
        plan = _plan(
            migrated_conn,
            "SELECT rowid FROM tasks_fts WHERE tasks_fts MATCH ?",
            ("keyset",),
        )
        assert "tasks_fts" in plan and "VIRTUAL TABLE INDEX" in plan, plan

    def test_dependents_query_uses_index(self, migrated_conn: sqlite3.Connection) -> None:
        plan = _plan(
            migrated_conn,
            "SELECT t.task_id FROM task_dependencies d "
            "JOIN tasks t ON t.task_id = d.task_id WHERE d.depends_on = ?",
            ("TASK-1",),
        )
        assert "idx_task_deps_depends_on" in plan, plan

    def test_trigger_maintains_junction_on_insert(self, migrated_conn: sqlite3.Connection) -> None:
        _seed_task(migrated_conn, "TASK-902", dependencies='["TASK-1", "TASK-2"]')
        deps = {
            r[0]
            for r in migrated_conn.execute(
                "SELECT depends_on FROM task_dependencies WHERE task_id = ?",
                ("TASK-902",),
            ).fetchall()
        }
        assert deps == {"TASK-1", "TASK-2"}

    def test_trigger_maintains_junction_on_update_and_delete(
        self, migrated_conn: sqlite3.Connection
    ) -> None:
        _seed_task(migrated_conn, "TASK-903", dependencies='["TASK-1"]')
        migrated_conn.execute(
            "UPDATE tasks SET dependencies = ? WHERE task_id = ?",
            ('["TASK-7", "TASK-8"]', "TASK-903"),
        )
        deps = {
            r[0]
            for r in migrated_conn.execute(
                "SELECT depends_on FROM task_dependencies WHERE task_id = ?",
                ("TASK-903",),
            ).fetchall()
        }
        assert deps == {"TASK-7", "TASK-8"}

        migrated_conn.execute("DELETE FROM tasks WHERE task_id = ?", ("TASK-903",))
        remaining = migrated_conn.execute(
            "SELECT COUNT(*) FROM task_dependencies WHERE task_id = ?", ("TASK-903",)
        ).fetchone()[0]
        assert remaining == 0

    def test_trigger_tolerates_empty_and_null_dependencies(
        self, migrated_conn: sqlite3.Connection
    ) -> None:
        # Neither NULL nor '' nor '[]' may break the json_each trigger.
        _seed_task(migrated_conn, "TASK-904", dependencies=None)
        _seed_task(migrated_conn, "TASK-905", dependencies="")
        _seed_task(migrated_conn, "TASK-906", dependencies="[]")
        count = migrated_conn.execute(
            "SELECT COUNT(*) FROM task_dependencies "
            "WHERE task_id IN ('TASK-904', 'TASK-905', 'TASK-906')"
        ).fetchone()[0]
        assert count == 0


class TestV38BackfillRework:
    """v38 un-starves learn_extract: a task with a backward move in
    task_status_history (reopened after testing/complete) is flipped from the
    hardcoded 'success' to the honest 'rework'. Clean tasks stay 'success'."""

    def _seed(self, conn, tid, outcome, reopened, old="testing"):
        conn.execute(
            "INSERT INTO task_outcomes (task_id, type, domain, complexity, outcome) "
            "VALUES (?, 'fix', 'INFRA', 'CLEAR', ?)",
            (tid, outcome),
        )
        if reopened:
            conn.execute(
                "INSERT INTO task_status_history (task_id, old_status, new_status, transitioned_at) "
                "VALUES (?, ?, 'in_progress', 0)",
                (tid, old),
            )

    def test_reopened_flipped_clean_unchanged(self, tmp_path: Path) -> None:
        from _db_migrations import _migrate_v38_backfill_rework_outcome

        db = tmp_path / ".coding-os" / "coding-os.db"
        db.parent.mkdir(parents=True)
        conn = init_db(db)
        self._seed(conn, "TASK-RW", "success", reopened=True, old="testing")
        self._seed(conn, "TASK-CP", "success", reopened=True, old="complete")
        self._seed(conn, "TASK-OK", "success", reopened=False)
        conn.commit()

        _migrate_v38_backfill_rework_outcome(conn)

        rows = {r[0]: r[1] for r in conn.execute("SELECT task_id, outcome FROM task_outcomes")}
        conn.close()
        assert rows["TASK-RW"] == "rework"  # reopened from testing
        assert rows["TASK-CP"] == "rework"  # reopened from complete
        assert rows["TASK-OK"] == "success"  # never reopened — untouched

    def test_idempotent(self, tmp_path: Path) -> None:
        from _db_migrations import _migrate_v38_backfill_rework_outcome

        db = tmp_path / ".coding-os" / "coding-os.db"
        db.parent.mkdir(parents=True)
        conn = init_db(db)
        self._seed(conn, "TASK-RW", "success", reopened=True)
        conn.commit()
        _migrate_v38_backfill_rework_outcome(conn)
        first = conn.execute(
            "SELECT outcome FROM task_outcomes WHERE task_id='TASK-RW'"
        ).fetchone()[0]
        _migrate_v38_backfill_rework_outcome(conn)  # second run = no-op
        second = conn.execute(
            "SELECT outcome FROM task_outcomes WHERE task_id='TASK-RW'"
        ).fetchone()[0]
        conn.close()
        assert first == second == "rework"


class TestV40EmbeddingOutbox:
    """v40 adds embedding_outbox — durable backlog for hot-path-skipped
    embeddings (Wave 4). Idempotent; UNIQUE(source_table, source_id)."""

    def test_table_created_and_idempotent(self, tmp_path: Path) -> None:
        from _db_migrations import _migrate_v40_embedding_outbox

        db = tmp_path / ".coding-os" / "coding-os.db"
        db.parent.mkdir(parents=True)
        conn = init_db(db)  # runs all migrations incl. v40
        assert (
            conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='embedding_outbox'"
            ).fetchone()
            is not None
        )
        # UNIQUE(source_table, source_id) enforced
        conn.execute(
            "INSERT INTO embedding_outbox (source_table, source_id, enqueued_at) "
            "VALUES ('observations', 1, 0)"
        )
        conn.execute(
            "INSERT OR IGNORE INTO embedding_outbox (source_table, source_id, enqueued_at) "
            "VALUES ('observations', 1, 0)"
        )
        conn.commit()
        assert conn.execute("SELECT COUNT(*) FROM embedding_outbox").fetchone()[0] == 1
        _migrate_v40_embedding_outbox(conn)  # re-run = no-op
        conn.close()
