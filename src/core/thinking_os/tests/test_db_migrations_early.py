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
    get_db_stats,
    get_schema_version,
    has_document_chunks_fts,
    has_embeddings_table,
    has_fts5,
    has_pattern_validations_table,
    has_tasks_table,
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


class TestMigrationV5RAG:
    def test_embeddings_table_created(self, migrated_conn: sqlite3.Connection) -> None:
        row = migrated_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='embeddings'"
        ).fetchone()
        assert row is not None

    def test_document_chunks_table_created(self, migrated_conn: sqlite3.Connection) -> None:
        row = migrated_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='document_chunks'"
        ).fetchone()
        assert row is not None

    def test_embeddings_columns(self, migrated_conn: sqlite3.Connection) -> None:
        cols = [row[1] for row in migrated_conn.execute("PRAGMA table_info(embeddings)").fetchall()]
        for required in (
            "id",
            "source_table",
            "source_id",
            "text_hash",
            "embedding",
            "model_name",
            "created_at",
        ):
            assert required in cols, f"embeddings missing column {required}"

    def test_document_chunks_columns(self, migrated_conn: sqlite3.Connection) -> None:
        cols = [
            row[1] for row in migrated_conn.execute("PRAGMA table_info(document_chunks)").fetchall()
        ]
        for required in (
            "id",
            "source_path",
            "source_type",
            "chunk_index",
            "heading_path",
            "content",
            "content_hash",
            "priority",
            "mtime",
            "created_at",
        ):
            assert required in cols, f"document_chunks missing column {required}"

    def test_embeddings_unique_constraint(self, migrated_conn: sqlite3.Connection) -> None:
        """UNIQUE(source_table, source_id) should prevent duplicate rows."""
        migrated_conn.execute(
            "INSERT INTO embeddings (source_table, source_id, text_hash, embedding) "
            "VALUES (?, ?, ?, ?)",
            ("observations", 1, "hash1", b"x" * 1536),
        )
        migrated_conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            migrated_conn.execute(
                "INSERT INTO embeddings (source_table, source_id, text_hash, embedding) "
                "VALUES (?, ?, ?, ?)",
                ("observations", 1, "hash2", b"y" * 1536),
            )
            migrated_conn.commit()

    def test_document_chunks_unique_constraint(self, migrated_conn: sqlite3.Connection) -> None:
        """UNIQUE(source_path, chunk_index) should prevent duplicate chunks."""
        migrated_conn.execute(
            "INSERT INTO document_chunks (source_path, source_type, chunk_index, content, content_hash, mtime) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("docs/PRD/01.md", "prd", 0, "content", "hash1", 1000),
        )
        migrated_conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            migrated_conn.execute(
                "INSERT INTO document_chunks (source_path, source_type, chunk_index, content, content_hash, mtime) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("docs/PRD/01.md", "prd", 0, "different content", "hash2", 2000),
            )
            migrated_conn.commit()

    def test_has_embeddings_table_true_after_migration(
        self, migrated_conn: sqlite3.Connection
    ) -> None:
        assert has_embeddings_table(migrated_conn) is True

    def test_has_embeddings_table_false_on_unmigrated(self, fresh_conn: sqlite3.Connection) -> None:
        assert has_embeddings_table(fresh_conn) is False

    def test_idx_embeddings_source_exists(self, migrated_conn: sqlite3.Connection) -> None:
        row = migrated_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_embeddings_source'"
        ).fetchone()
        assert row is not None

    def test_idx_doc_chunks_path_exists(self, migrated_conn: sqlite3.Connection) -> None:
        row = migrated_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_doc_chunks_path'"
        ).fetchone()
        assert row is not None

    def test_v5_idempotent(self, fresh_conn: sqlite3.Connection) -> None:
        """Running migrations twice should not error or duplicate v5 tables."""
        run_migrations(fresh_conn)
        run_migrations(fresh_conn)  # second run should be a no-op
        assert has_embeddings_table(fresh_conn) is True


class TestMigrationV6Tasks:
    def test_tasks_table_created(self, migrated_conn: sqlite3.Connection) -> None:
        row = migrated_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='tasks'"
        ).fetchone()
        assert row is not None

    def test_tasks_columns(self, migrated_conn: sqlite3.Connection) -> None:
        cols = {row[1] for row in migrated_conn.execute("PRAGMA table_info(tasks)").fetchall()}
        expected = {
            "task_id",
            "title",
            "domain",
            "status",
            "file_path",
            "content_hash",
            "mtime",
            "goal_text",
            "dependencies",
            "blocked_by_json",
            "references_json",
            "external_ref",
            "created_at",
            "updated_at",
        }
        missing = expected - cols
        assert not missing, f"tasks table missing columns: {missing}"
        # v41 dropped the v6-era columns nothing read or wrote after the
        # legacy task_sync retirement (TASK-398).
        dropped = {
            "scope_in",
            "scope_out",
            "requirements",
            "source_of_truth",
            "open_questions",
            "rabbit_holes",
            "verification",
            "read_first",
        }
        assert not (dropped & cols), f"v41 should have dropped: {dropped & cols}"

    def test_tasks_primary_key_is_task_id(self, migrated_conn: sqlite3.Connection) -> None:
        """task_id should be the PRIMARY KEY — inserting a duplicate raises."""
        migrated_conn.execute(
            "INSERT INTO tasks (task_id, title, file_path, content_hash, mtime) "
            "VALUES (?, ?, ?, ?, ?)",
            ("TASK-001", "first", "docs/tasks/TASK-001.md", "hash1", 1000),
        )
        with pytest.raises(sqlite3.IntegrityError):
            migrated_conn.execute(
                "INSERT INTO tasks (task_id, title, file_path, content_hash, mtime) "
                "VALUES (?, ?, ?, ?, ?)",
                ("TASK-001", "duplicate", "docs/tasks/TASK-001.md", "hash2", 1001),
            )

    def test_tasks_indexes_exist(self, migrated_conn: sqlite3.Connection) -> None:
        indexes = {
            row[0]
            for row in migrated_conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()
        }
        assert "idx_tasks_status" in indexes
        assert "idx_tasks_domain" in indexes
        assert "idx_tasks_file_path" in indexes

    def test_has_tasks_table_true_after_migration(self, migrated_conn: sqlite3.Connection) -> None:
        assert has_tasks_table(migrated_conn) is True

    def test_has_tasks_table_false_on_unmigrated(self, fresh_conn: sqlite3.Connection) -> None:
        assert has_tasks_table(fresh_conn) is False

    def test_v6_idempotent(self, fresh_conn: sqlite3.Connection) -> None:
        """Running migrations twice should not error or duplicate v6 objects."""
        run_migrations(fresh_conn)
        run_migrations(fresh_conn)
        assert has_tasks_table(fresh_conn) is True
        # v6+ must be applied (later migrations may push the number higher)
        assert get_schema_version(fresh_conn) >= 6

    def test_tasks_in_get_db_stats(self, migrated_conn: sqlite3.Connection) -> None:
        stats = get_db_stats(migrated_conn)
        assert "tasks" in stats["tables"]
        assert stats["tables"]["tasks"] == 0


class TestMigrationV8ValidationThrottle:
    def test_schema_version_at_least_8(self, migrated_conn: sqlite3.Connection) -> None:
        assert get_schema_version(migrated_conn) >= 8

    def test_pattern_validations_table_exists(self, migrated_conn: sqlite3.Connection) -> None:
        row = migrated_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='pattern_validations'"
        ).fetchone()
        assert row is not None

    def test_pattern_validations_columns(self, migrated_conn: sqlite3.Connection) -> None:
        cols = {
            row[1]
            for row in migrated_conn.execute("PRAGMA table_info(pattern_validations)").fetchall()
        }
        expected = {
            "id",
            "session_id",
            "pattern_id",
            "was_helpful",
            "was_throttled",
            "created_at",
        }
        missing = expected - cols
        assert not missing, f"pattern_validations missing columns: {missing}"

    def test_pattern_validations_indexes(self, migrated_conn: sqlite3.Connection) -> None:
        indexes = {
            row[0]
            for row in migrated_conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()
        }
        assert "idx_pattern_validations_session_pattern" in indexes
        assert "idx_pattern_validations_created" in indexes

    def test_has_pattern_validations_table_true(self, migrated_conn: sqlite3.Connection) -> None:
        assert has_pattern_validations_table(migrated_conn) is True

    def test_has_pattern_validations_table_false_on_fresh(
        self, fresh_conn: sqlite3.Connection
    ) -> None:
        assert has_pattern_validations_table(fresh_conn) is False

    def test_pattern_validations_in_db_stats(self, migrated_conn: sqlite3.Connection) -> None:
        stats = get_db_stats(migrated_conn)
        assert "pattern_validations" in stats["tables"]
        assert stats["tables"]["pattern_validations"] == 0

    def test_v8_idempotent(self, fresh_conn: sqlite3.Connection) -> None:
        run_migrations(fresh_conn)
        run_migrations(fresh_conn)
        assert has_pattern_validations_table(fresh_conn) is True
        assert get_schema_version(fresh_conn) >= 8


class TestMigrationV9DocsFTS:
    def test_schema_version_at_least_9(self, migrated_conn: sqlite3.Connection) -> None:
        assert get_schema_version(migrated_conn) >= 9

    def test_document_chunks_fts_exists_when_fts5_available(
        self, migrated_conn: sqlite3.Connection
    ) -> None:
        if not has_fts5(migrated_conn):
            pytest.skip("FTS5 not available on this build")
        assert has_document_chunks_fts(migrated_conn) is True

    def test_has_document_chunks_fts_false_on_fresh(self, fresh_conn: sqlite3.Connection) -> None:
        assert has_document_chunks_fts(fresh_conn) is False

    def test_fts_triggers_installed(self, migrated_conn: sqlite3.Connection) -> None:
        if not has_fts5(migrated_conn):
            pytest.skip("FTS5 not available on this build")
        triggers = {
            row[0]
            for row in migrated_conn.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger'"
            ).fetchall()
        }
        assert "document_chunks_ai" in triggers
        assert "document_chunks_au" in triggers
        assert "document_chunks_ad" in triggers

    def test_fts_insert_trigger_syncs_row(self, migrated_conn: sqlite3.Connection) -> None:
        if not has_fts5(migrated_conn):
            pytest.skip("FTS5 not available on this build")
        migrated_conn.execute(
            "INSERT INTO document_chunks "
            "(source_path, source_type, chunk_index, heading_path, content, "
            "content_hash, mtime) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "docs/x.md",
                "engineering",
                0,
                "X > Intro",
                "upsert_embedding handles retries",
                "h",
                1,
            ),
        )
        migrated_conn.commit()

        # FTS5 MATCH must find the row inserted through the trigger.
        hits = migrated_conn.execute(
            "SELECT rowid FROM document_chunks_fts WHERE document_chunks_fts MATCH ?",
            ("upsert_embedding",),
        ).fetchall()
        assert len(hits) == 1

    def test_v9_idempotent(self, fresh_conn: sqlite3.Connection) -> None:
        run_migrations(fresh_conn)
        run_migrations(fresh_conn)
        assert get_schema_version(fresh_conn) >= 9
