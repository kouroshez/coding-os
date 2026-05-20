"""
Tests for FTS5 full-text search layer (TASK-152).

Tests migration v2, FTS5 triggers (INSERT/UPDATE/DELETE), graceful degradation.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import (
    get_connection,
    get_schema_version,
    has_fts5,
    has_fts5_table,
    init_db,
    run_migrations,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def migrated_conn(tmp_path: Path) -> sqlite3.Connection:
    """Return a connection with all migrations (v1 + v2) applied."""
    conn = init_db(tmp_path / "test.db")
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# Migration v2
# ---------------------------------------------------------------------------


class TestMigrationV2:
    def test_schema_version_includes_fts5(self, migrated_conn: sqlite3.Connection) -> None:
        assert get_schema_version(migrated_conn) >= 2

    def test_fts5_table_exists(self, migrated_conn: sqlite3.Connection) -> None:
        if not has_fts5(migrated_conn):
            pytest.skip("FTS5 not available in this SQLite build")
        assert has_fts5_table(migrated_conn)

    def test_triggers_exist(self, migrated_conn: sqlite3.Connection) -> None:
        if not has_fts5(migrated_conn):
            pytest.skip("FTS5 not available")
        triggers = [
            row[0]
            for row in migrated_conn.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger'"
            ).fetchall()
        ]
        assert "observations_ai" in triggers
        assert "observations_au" in triggers
        assert "observations_ad" in triggers

    def test_migration_idempotent(self, tmp_path: Path) -> None:
        conn = init_db(tmp_path / "test.db")
        try:
            version_1 = get_schema_version(conn)
            applied = run_migrations(conn)
            version_2 = get_schema_version(conn)
            assert version_1 == version_2
            assert len(applied) == 0
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# FTS5 INSERT trigger
# ---------------------------------------------------------------------------


class TestFTS5Insert:
    def test_insert_populates_fts(self, migrated_conn: sqlite3.Connection) -> None:
        if not has_fts5_table(migrated_conn):
            pytest.skip("FTS5 not available")
        migrated_conn.execute(
            "INSERT INTO observations (title, narrative, concepts) VALUES (?, ?, ?)",
            (
                "Django migration fix",
                "Fixed missing migration for User model",
                '["django","migration"]',
            ),
        )
        migrated_conn.commit()

        results = migrated_conn.execute(
            "SELECT * FROM observations_fts WHERE observations_fts MATCH 'django'",
        ).fetchall()
        assert len(results) == 1

    def test_fts_search_by_narrative(self, migrated_conn: sqlite3.Connection) -> None:
        if not has_fts5_table(migrated_conn):
            pytest.skip("FTS5 not available")
        migrated_conn.execute(
            "INSERT INTO observations (title, narrative, concepts) VALUES (?, ?, ?)",
            (
                "Config change",
                "Updated PostgreSQL connection pooling settings",
                '["postgres","config"]',
            ),
        )
        migrated_conn.commit()

        results = migrated_conn.execute(
            "SELECT * FROM observations_fts WHERE observations_fts MATCH 'PostgreSQL'",
        ).fetchall()
        assert len(results) == 1

    def test_fts_search_by_concepts(self, migrated_conn: sqlite3.Connection) -> None:
        if not has_fts5_table(migrated_conn):
            pytest.skip("FTS5 not available")
        migrated_conn.execute(
            "INSERT INTO observations (title, narrative, concepts) VALUES (?, ?, ?)",
            ("API endpoint", "Added new REST endpoint", '["api","rest","endpoint"]'),
        )
        migrated_conn.commit()

        results = migrated_conn.execute(
            "SELECT * FROM observations_fts WHERE observations_fts MATCH 'endpoint'",
        ).fetchall()
        assert len(results) == 1

    def test_fts_no_match(self, migrated_conn: sqlite3.Connection) -> None:
        if not has_fts5_table(migrated_conn):
            pytest.skip("FTS5 not available")
        migrated_conn.execute(
            "INSERT INTO observations (title, narrative, concepts) VALUES (?, ?, ?)",
            ("Test obs", "Some narrative", '["test"]'),
        )
        migrated_conn.commit()

        results = migrated_conn.execute(
            "SELECT * FROM observations_fts WHERE observations_fts MATCH 'nonexistent'",
        ).fetchall()
        assert len(results) == 0

    def test_multiple_inserts_all_searchable(self, migrated_conn: sqlite3.Connection) -> None:
        if not has_fts5_table(migrated_conn):
            pytest.skip("FTS5 not available")
        for i in range(5):
            migrated_conn.execute(
                "INSERT INTO observations (title, narrative, concepts) VALUES (?, ?, ?)",
                (f"Obs {i}", f"Batch observation number {i}", f'["batch","item{i}"]'),
            )
        migrated_conn.commit()

        results = migrated_conn.execute(
            "SELECT * FROM observations_fts WHERE observations_fts MATCH 'batch'",
        ).fetchall()
        assert len(results) == 5


# ---------------------------------------------------------------------------
# FTS5 UPDATE trigger
# ---------------------------------------------------------------------------


class TestFTS5Update:
    def test_update_syncs_to_fts(self, migrated_conn: sqlite3.Connection) -> None:
        if not has_fts5_table(migrated_conn):
            pytest.skip("FTS5 not available")
        migrated_conn.execute(
            "INSERT INTO observations (title, narrative, concepts) VALUES (?, ?, ?)",
            ("Unique alpha title", "Unique alpha narrative", '["alpha"]'),
        )
        migrated_conn.commit()

        # Update all fields so old text is fully replaced
        migrated_conn.execute(
            "UPDATE observations SET title = ?, narrative = ?, concepts = ? WHERE title = ?",
            ("Beta title", "Compressed narrative about caching", '["beta"]', "Unique alpha title"),
        )
        migrated_conn.commit()

        # Old unique text should not match
        old_results = migrated_conn.execute(
            "SELECT * FROM observations_fts WHERE observations_fts MATCH 'alpha'",
        ).fetchall()
        assert len(old_results) == 0

        # New text should match
        new_results = migrated_conn.execute(
            "SELECT * FROM observations_fts WHERE observations_fts MATCH 'caching'",
        ).fetchall()
        assert len(new_results) == 1


# ---------------------------------------------------------------------------
# FTS5 DELETE trigger
# ---------------------------------------------------------------------------


class TestFTS5Delete:
    def test_delete_removes_from_fts(self, migrated_conn: sqlite3.Connection) -> None:
        if not has_fts5_table(migrated_conn):
            pytest.skip("FTS5 not available")
        migrated_conn.execute(
            "INSERT INTO observations (title, narrative, concepts) VALUES (?, ?, ?)",
            ("To be deleted", "This will be removed", '["delete"]'),
        )
        migrated_conn.commit()

        # Verify it's in FTS
        results = migrated_conn.execute(
            "SELECT * FROM observations_fts WHERE observations_fts MATCH 'removed'",
        ).fetchall()
        assert len(results) == 1

        # Delete
        migrated_conn.execute("DELETE FROM observations WHERE title = 'To be deleted'")
        migrated_conn.commit()

        # Verify gone from FTS
        results = migrated_conn.execute(
            "SELECT * FROM observations_fts WHERE observations_fts MATCH 'removed'",
        ).fetchall()
        assert len(results) == 0


# ---------------------------------------------------------------------------
# has_fts5_table helper
# ---------------------------------------------------------------------------


class TestHasFTS5Table:
    def test_returns_true_after_migration(self, migrated_conn: sqlite3.Connection) -> None:
        if not has_fts5(migrated_conn):
            pytest.skip("FTS5 not available")
        assert has_fts5_table(migrated_conn) is True

    def test_returns_false_on_fresh_v1_db(self, tmp_path: Path) -> None:
        """On a DB with only v1 migration, FTS5 table should not exist."""
        conn = get_connection(tmp_path / "v1only.db")
        try:
            # Manually apply only v1
            from database import MIGRATIONS, _ensure_version_table

            _ensure_version_table(conn)
            version, description, sql = MIGRATIONS[0]
            conn.executescript(sql)
            conn.execute(
                "INSERT INTO schema_version (version, description) VALUES (?, ?)",
                (version, description),
            )
            conn.commit()
            assert has_fts5_table(conn) is False
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# FTS5 ranking (basic)
# ---------------------------------------------------------------------------


class TestFTS5Ranking:
    def test_rank_function_available(self, migrated_conn: sqlite3.Connection) -> None:
        if not has_fts5_table(migrated_conn):
            pytest.skip("FTS5 not available")
        migrated_conn.execute(
            "INSERT INTO observations (title, narrative, concepts) VALUES (?, ?, ?)",
            ("Django ORM", "Django ORM query optimization", '["django","orm"]'),
        )
        migrated_conn.execute(
            "INSERT INTO observations (title, narrative, concepts) VALUES (?, ?, ?)",
            ("React hooks", "React hooks for state management", '["react","hooks"]'),
        )
        migrated_conn.commit()

        # rank is a built-in FTS5 function
        results = migrated_conn.execute(
            "SELECT *, rank FROM observations_fts WHERE observations_fts MATCH 'Django' ORDER BY rank",
        ).fetchall()
        assert len(results) == 1
