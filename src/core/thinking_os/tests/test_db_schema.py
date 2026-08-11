"""
Tests for db.py — migration, WAL mode, table creation, FTS5 detection.

TASK-141: Unit tests for the database module.
"""

from __future__ import annotations

import json
import sqlite3

# Adjust path so we can import from parent
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import (
    MIGRATIONS,
    get_connection,
    get_db_stats,
    get_schema_version,
    has_fts5,
    init_db,
    run_migrations,
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


class TestPragmas:
    def test_wal_mode_enabled(self, fresh_conn: sqlite3.Connection) -> None:
        mode = fresh_conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "wal"

    def test_foreign_keys_enabled(self, fresh_conn: sqlite3.Connection) -> None:
        fk = fresh_conn.execute("PRAGMA foreign_keys").fetchone()[0]
        assert fk == 1

    def test_synchronous_normal(self, fresh_conn: sqlite3.Connection) -> None:
        sync = fresh_conn.execute("PRAGMA synchronous").fetchone()[0]
        assert sync == 1  # NORMAL = 1

    def test_temp_store_memory(self, fresh_conn: sqlite3.Connection) -> None:
        ts = fresh_conn.execute("PRAGMA temp_store").fetchone()[0]
        assert ts == 2  # MEMORY = 2


class TestSchemaVersioning:
    def test_fresh_db_version_is_zero(self, fresh_conn: sqlite3.Connection) -> None:
        version = get_schema_version(fresh_conn)
        assert version == 0

    def test_after_migration_version_is_latest(self, fresh_conn: sqlite3.Connection) -> None:
        run_migrations(fresh_conn)
        version = get_schema_version(fresh_conn)
        assert version == len(MIGRATIONS)

    def test_migrations_are_idempotent(self, fresh_conn: sqlite3.Connection) -> None:
        applied_1 = run_migrations(fresh_conn)
        applied_2 = run_migrations(fresh_conn)
        assert len(applied_1) == len(MIGRATIONS)
        assert len(applied_2) == 0
        assert get_schema_version(fresh_conn) == len(MIGRATIONS)

    def test_v49_backfills_times_seen_from_times_validated(self) -> None:
        from _db_migrations import _migrate_v49_add_times_seen

        conn = sqlite3.connect(":memory:")
        conn.execute(
            "CREATE TABLE learned_patterns (id INTEGER PRIMARY KEY, times_validated INTEGER DEFAULT 0)"
        )
        conn.execute("INSERT INTO learned_patterns (times_validated) VALUES (7)")
        conn.commit()
        _migrate_v49_add_times_seen(conn)
        seen = conn.execute("SELECT times_seen FROM learned_patterns").fetchone()[0]
        conn.close()
        assert seen == 7

    def test_v50_rebuilds_times_validated_from_ledger(self) -> None:
        from _db_migrations import _migrate_v50_reset_times_validated_from_ledger

        conn = sqlite3.connect(":memory:")
        conn.execute(
            "CREATE TABLE learned_patterns (id INTEGER PRIMARY KEY, times_validated INTEGER DEFAULT 0)"
        )
        conn.execute(
            "CREATE TABLE pattern_validations (id INTEGER PRIMARY KEY, pattern_id INTEGER, "
            "was_helpful INTEGER, was_throttled INTEGER DEFAULT 0)"
        )
        # p1: inflated pre-split counter, no real validations → honest zero.
        # p2: inflated counter, ledger has 2 helpful + 1 throttled + 1 unhelpful → 2.
        conn.executemany(
            "INSERT INTO learned_patterns (id, times_validated) VALUES (?, ?)", [(1, 500), (2, 500)]
        )
        conn.executemany(
            "INSERT INTO pattern_validations (pattern_id, was_helpful, was_throttled) VALUES (?, ?, ?)",
            [(2, 1, 0), (2, 1, 0), (2, 1, 1), (2, 0, 0)],
        )
        conn.commit()
        _migrate_v50_reset_times_validated_from_ledger(conn)
        rows = dict(conn.execute("SELECT id, times_validated FROM learned_patterns").fetchall())
        conn.close()
        assert rows[1] == 0  # no ledger rows → inflated value retired to honest zero
        assert rows[2] == 2  # only helpful, non-throttled validations count

    def test_v51_partial_unique_index_makes_dedup_atomic(
        self, migrated_conn: sqlite3.Connection
    ) -> None:
        conn = migrated_conn
        idx = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' "
            "AND name='idx_observations_content_session'"
        ).fetchone()
        assert idx is not None, "partial unique index missing after migrations"
        # Race-loser: a second INSERT OR IGNORE for the same (content_hash, session_id)
        # is silently ignored (rowcount 0), so only one row survives.
        conn.execute(
            "INSERT OR IGNORE INTO observations (session_id, title, content_hash) VALUES ('S','a','H')"
        )
        cur = conn.execute(
            "INSERT OR IGNORE INTO observations (session_id, title, content_hash) VALUES ('S','b','H')"
        )
        conn.commit()
        assert cur.rowcount == 0
        assert (
            conn.execute("SELECT COUNT(*) FROM observations WHERE content_hash='H'").fetchone()[0]
            == 1
        )
        # NULLs are exempt (not dedup targets).
        for _ in range(2):
            conn.execute("INSERT OR IGNORE INTO observations (session_id, title) VALUES ('S','n')")
        conn.commit()
        assert (
            conn.execute("SELECT COUNT(*) FROM observations WHERE content_hash IS NULL").fetchone()[
                0
            ]
            == 2
        )

    def test_v51_collapses_existing_duplicates_keeping_earliest(
        self, migrated_conn: sqlite3.Connection
    ) -> None:
        from _db_migrations import _migrate_v51_observations_dedup_unique

        conn = migrated_conn
        conn.execute("DROP INDEX idx_observations_content_session")
        ids = [
            conn.execute(
                "INSERT INTO observations (session_id, title, content_hash) VALUES ('D',?,'HD')",
                (f"d{i}",),
            ).lastrowid
            for i in range(3)
        ]
        conn.commit()
        _migrate_v51_observations_dedup_unique(conn)
        rows = conn.execute("SELECT id FROM observations WHERE content_hash='HD'").fetchall()
        assert len(rows) == 1 and rows[0][0] == min(ids), "must collapse to the earliest id"

    def test_version_table_records_description(self, migrated_conn: sqlite3.Connection) -> None:
        row = migrated_conn.execute(
            "SELECT description FROM schema_version WHERE version = 1"
        ).fetchone()
        assert row is not None
        assert "TASK-141" in row[0]


EXPECTED_TABLES = [
    "task_outcomes",
    "agent_metrics",
    "learned_patterns",
    "observations",
    "session_summaries",
    "schema_version",
    "log_events",
    "log_fingerprints",
    "task_dependencies",
    "adapter_health",
]


class TestTableCreation:
    def test_all_tables_exist(self, migrated_conn: sqlite3.Connection) -> None:
        tables = [
            row[0]
            for row in migrated_conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
        ]
        for expected in EXPECTED_TABLES:
            assert expected in tables, f"Table '{expected}' not found. Got: {tables}"

    def test_task_outcomes_columns(self, migrated_conn: sqlite3.Connection) -> None:
        cols = [
            row[1] for row in migrated_conn.execute("PRAGMA table_info(task_outcomes)").fetchall()
        ]
        assert "task_id" in cols
        assert "outcome" in cols
        assert "complexity" in cols
        assert "skills_used" in cols

    def test_observations_columns(self, migrated_conn: sqlite3.Connection) -> None:
        cols = [
            row[1] for row in migrated_conn.execute("PRAGMA table_info(observations)").fetchall()
        ]
        assert "session_id" in cols
        assert "content_hash" in cols
        assert "impact_score" in cols
        assert "concepts" in cols
        assert "expires_at" in cols

    def test_learned_patterns_columns(self, migrated_conn: sqlite3.Connection) -> None:
        cols = [
            row[1]
            for row in migrated_conn.execute("PRAGMA table_info(learned_patterns)").fetchall()
        ]
        assert "confidence" in cols
        assert "decay_rate" in cols
        assert "impact_score" in cols
        assert "concepts" in cols
        assert "access_count" in cols

    def test_formula_dispatches_has_error_column(self, migrated_conn: sqlite3.Connection) -> None:
        # B5 (v34): failed dispatches must be diagnosable, not logged-only.
        cols = [
            row[1]
            for row in migrated_conn.execute("PRAGMA table_info(formula_dispatches)").fetchall()
        ]
        assert "error" in cols
        assert "status" in cols
        assert "cost_usd" in cols

    def test_formula_dispatches_has_supervised_identity_columns(
        self, migrated_conn: sqlite3.Connection
    ) -> None:
        cols = {
            row[1]
            for row in migrated_conn.execute("PRAGMA table_info(formula_dispatches)").fetchall()
        }
        assert {
            "adapter",
            "effort",
            "error_category",
            "retry_after_s",
            "health_state",
            "health_probe",
        } <= cols


class TestDataOperations:
    def test_insert_task_outcome(self, migrated_conn: sqlite3.Connection) -> None:
        migrated_conn.execute(
            "INSERT INTO task_outcomes (task_id, type, domain, complexity, outcome) "
            "VALUES (?, ?, ?, ?, ?)",
            ("TASK-100", "feat", "BACKEND", "CLEAR", "success"),
        )
        migrated_conn.commit()
        row = migrated_conn.execute(
            "SELECT * FROM task_outcomes WHERE task_id = ?", ("TASK-100",)
        ).fetchone()
        assert row is not None
        assert row["outcome"] == "success"

    def test_insert_observation(self, migrated_conn: sqlite3.Connection) -> None:
        migrated_conn.execute(
            "INSERT INTO observations (session_id, tool_name, title, concepts) VALUES (?, ?, ?, ?)",
            ("sess-001", "Read", "Read config file", '["config","settings"]'),
        )
        migrated_conn.commit()
        row = migrated_conn.execute(
            "SELECT * FROM observations WHERE session_id = ?", ("sess-001",)
        ).fetchone()
        assert row is not None
        concepts = json.loads(row["concepts"])
        assert "config" in concepts

    def test_insert_learned_pattern(self, migrated_conn: sqlite3.Connection) -> None:
        migrated_conn.execute(
            "INSERT INTO learned_patterns (pattern, domain, confidence) VALUES (?, ?, ?)",
            ("Always use services layer for DB writes", "BACKEND", 0.6),
        )
        migrated_conn.commit()
        row = migrated_conn.execute(
            "SELECT * FROM learned_patterns WHERE domain = ?", ("BACKEND",)
        ).fetchone()
        assert row is not None
        assert row["confidence"] == 0.6


class TestFTS5Detection:
    def test_fts5_returns_bool(self, migrated_conn: sqlite3.Connection) -> None:
        result = has_fts5(migrated_conn)
        assert isinstance(result, bool)

    def test_fts5_probe_table_cleaned_up(self, migrated_conn: sqlite3.Connection) -> None:
        has_fts5(migrated_conn)
        tables = [
            row[0]
            for row in migrated_conn.execute(
                "SELECT name FROM sqlite_master WHERE name = '_fts5_probe'"
            ).fetchall()
        ]
        assert len(tables) == 0


class TestDbStats:
    def test_stats_returns_all_tables(self, migrated_conn: sqlite3.Connection) -> None:
        stats = get_db_stats(migrated_conn)
        assert "tables" in stats
        for table in [
            "task_outcomes",
            "agent_metrics",
            "learned_patterns",
            "observations",
            "session_summaries",
        ]:
            assert table in stats["tables"]
            assert stats["tables"][table] == 0  # fresh DB

    def test_stats_includes_version(self, migrated_conn: sqlite3.Connection) -> None:
        stats = get_db_stats(migrated_conn)
        assert stats["schema_version"] == len(MIGRATIONS)

    def test_stats_includes_fts5(self, migrated_conn: sqlite3.Connection) -> None:
        stats = get_db_stats(migrated_conn)
        assert "fts5_available" in stats
        assert isinstance(stats["fts5_available"], bool)

    def test_stats_includes_db_size(self, migrated_conn: sqlite3.Connection) -> None:
        stats = get_db_stats(migrated_conn)
        assert "db_size_bytes" in stats
        assert stats["db_size_bytes"] >= 0

    def test_stats_after_insert(self, migrated_conn: sqlite3.Connection) -> None:
        migrated_conn.execute(
            "INSERT INTO task_outcomes (task_id, type, domain, complexity, outcome) "
            "VALUES (?, ?, ?, ?, ?)",
            ("TASK-200", "fix", "FRONTEND", "COMPLICATED", "success"),
        )
        migrated_conn.commit()
        stats = get_db_stats(migrated_conn)
        assert stats["tables"]["task_outcomes"] == 1


class TestInitDb:
    def test_init_db_creates_file(self, tmp_db_path: Path) -> None:
        conn = init_db(tmp_db_path)
        try:
            assert tmp_db_path.exists()
        finally:
            conn.close()

    def test_init_db_returns_migrated_connection(self, tmp_db_path: Path) -> None:
        conn = init_db(tmp_db_path)
        try:
            version = get_schema_version(conn)
            assert version == len(MIGRATIONS)
        finally:
            conn.close()
