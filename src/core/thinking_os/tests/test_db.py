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
    PROTECTED_TRUST_TIERS,
    VALID_PROVENANCE,
    VALID_TRUST_TIERS,
    get_connection,
    get_db_stats,
    get_schema_version,
    has_document_chunks_fts,
    has_embeddings_table,
    has_fts5,
    has_memory_audit_table,
    has_pattern_validations_table,
    has_tasks_table,
    init_db,
    is_pattern_protected,
    record_audit,
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


# ---------------------------------------------------------------------------
# Schema versioning
# ---------------------------------------------------------------------------


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

    def test_version_table_records_description(self, migrated_conn: sqlite3.Connection) -> None:
        row = migrated_conn.execute(
            "SELECT description FROM schema_version WHERE version = 1"
        ).fetchone()
        assert row is not None
        assert "TASK-141" in row[0]


# ---------------------------------------------------------------------------
# Table creation
# ---------------------------------------------------------------------------

EXPECTED_TABLES = [
    "task_outcomes",
    "agent_metrics",
    "learned_patterns",
    "experiment_log",
    "observations",
    "session_summaries",
    "schema_version",
    "log_events",
    "log_fingerprints",
    "task_dependencies",
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


# ---------------------------------------------------------------------------
# Data insertion smoke test
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# FTS5 detection
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Stats helper
# ---------------------------------------------------------------------------


class TestDbStats:
    def test_stats_returns_all_tables(self, migrated_conn: sqlite3.Connection) -> None:
        stats = get_db_stats(migrated_conn)
        assert "tables" in stats
        for table in [
            "task_outcomes",
            "agent_metrics",
            "learned_patterns",
            "experiment_log",
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


# ---------------------------------------------------------------------------
# init_db integration
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Migration v5 — RAG (embeddings + document_chunks)
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


# ---------------------------------------------------------------------------
# Migration v6 — Task Store
# ---------------------------------------------------------------------------


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
            "scope_in",
            "scope_out",
            "requirements",
            "dependencies",
            "source_of_truth",
            "read_first",
            "open_questions",
            "rabbit_holes",
            "verification",
            "created_at",
            "updated_at",
        }
        missing = expected - cols
        assert not missing, f"tasks table missing columns: {missing}"

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


# ---------------------------------------------------------------------------
# Migration v7 — Brain Hardening (trust_tier, provenance, memory_audit)
# ---------------------------------------------------------------------------


class TestMigrationV7BrainHardening:
    def test_schema_version_at_least_7(self, migrated_conn: sqlite3.Connection) -> None:
        assert get_schema_version(migrated_conn) >= 7

    def test_learned_patterns_has_trust_tier(self, migrated_conn: sqlite3.Connection) -> None:
        cols = {
            row[1]
            for row in migrated_conn.execute("PRAGMA table_info(learned_patterns)").fetchall()
        }
        assert "trust_tier" in cols

    def test_learned_patterns_has_provenance(self, migrated_conn: sqlite3.Connection) -> None:
        cols = {
            row[1]
            for row in migrated_conn.execute("PRAGMA table_info(learned_patterns)").fetchall()
        }
        assert "provenance" in cols

    def test_observations_has_provenance(self, migrated_conn: sqlite3.Connection) -> None:
        cols = {
            row[1] for row in migrated_conn.execute("PRAGMA table_info(observations)").fetchall()
        }
        assert "provenance" in cols

    def test_memory_audit_table_exists(self, migrated_conn: sqlite3.Connection) -> None:
        row = migrated_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='memory_audit'"
        ).fetchone()
        assert row is not None

    def test_has_memory_audit_table_true_on_migrated(
        self, migrated_conn: sqlite3.Connection
    ) -> None:
        assert has_memory_audit_table(migrated_conn) is True

    def test_has_memory_audit_table_false_on_fresh(self, fresh_conn: sqlite3.Connection) -> None:
        assert has_memory_audit_table(fresh_conn) is False

    def test_default_trust_tier_is_volatile(self, migrated_conn: sqlite3.Connection) -> None:
        migrated_conn.execute(
            "INSERT INTO learned_patterns (pattern) VALUES (?)",
            ("test pattern",),
        )
        row = migrated_conn.execute(
            "SELECT trust_tier FROM learned_patterns WHERE pattern = ?",
            ("test pattern",),
        ).fetchone()
        assert row[0] == "volatile"

    def test_default_provenance_is_agent_self(self, migrated_conn: sqlite3.Connection) -> None:
        migrated_conn.execute(
            "INSERT INTO learned_patterns (pattern) VALUES (?)",
            ("pattern-prov",),
        )
        row = migrated_conn.execute(
            "SELECT provenance FROM learned_patterns WHERE pattern = ?",
            ("pattern-prov",),
        ).fetchone()
        assert row[0] == "agent_self"

    def test_observations_default_provenance(self, migrated_conn: sqlite3.Connection) -> None:
        migrated_conn.execute(
            "INSERT INTO observations (title, narrative) VALUES (?, ?)",
            ("t", "n"),
        )
        row = migrated_conn.execute(
            "SELECT provenance FROM observations WHERE title = 't'"
        ).fetchone()
        assert row[0] == "agent_self"

    def test_locked_pattern_update_blocked(self, migrated_conn: sqlite3.Connection) -> None:
        """UPDATE on a locked pattern must raise via the protection trigger."""
        cursor = migrated_conn.execute(
            "INSERT INTO learned_patterns (pattern, trust_tier) VALUES (?, ?)",
            ("locked-rule", "locked"),
        )
        pattern_id = cursor.lastrowid
        migrated_conn.commit()

        with pytest.raises(sqlite3.IntegrityError):
            migrated_conn.execute(
                "UPDATE learned_patterns SET confidence = 0.1 WHERE id = ?",
                (pattern_id,),
            )

    def test_core_pattern_update_blocked(self, migrated_conn: sqlite3.Connection) -> None:
        cursor = migrated_conn.execute(
            "INSERT INTO learned_patterns (pattern, trust_tier) VALUES (?, ?)",
            ("core-governance", "core"),
        )
        pattern_id = cursor.lastrowid
        migrated_conn.commit()

        with pytest.raises(sqlite3.IntegrityError):
            migrated_conn.execute(
                "UPDATE learned_patterns SET pattern = 'hacked' WHERE id = ?",
                (pattern_id,),
            )

    def test_locked_pattern_delete_blocked(self, migrated_conn: sqlite3.Connection) -> None:
        cursor = migrated_conn.execute(
            "INSERT INTO learned_patterns (pattern, trust_tier) VALUES (?, ?)",
            ("locked-del", "locked"),
        )
        pattern_id = cursor.lastrowid
        migrated_conn.commit()

        with pytest.raises(sqlite3.IntegrityError):
            migrated_conn.execute("DELETE FROM learned_patterns WHERE id = ?", (pattern_id,))

    def test_volatile_pattern_update_allowed(self, migrated_conn: sqlite3.Connection) -> None:
        """Baseline: volatile rows are mutable as before (no regression)."""
        cursor = migrated_conn.execute(
            "INSERT INTO learned_patterns (pattern) VALUES (?)",
            ("volatile-one",),
        )
        pattern_id = cursor.lastrowid
        migrated_conn.commit()

        migrated_conn.execute(
            "UPDATE learned_patterns SET confidence = 0.42 WHERE id = ?",
            (pattern_id,),
        )
        row = migrated_conn.execute(
            "SELECT confidence FROM learned_patterns WHERE id = ?",
            (pattern_id,),
        ).fetchone()
        assert abs(row[0] - 0.42) < 1e-6

    def test_validated_pattern_update_allowed(self, migrated_conn: sqlite3.Connection) -> None:
        """Only locked/core are protected — validated rows still mutable."""
        cursor = migrated_conn.execute(
            "INSERT INTO learned_patterns (pattern, trust_tier) VALUES (?, ?)",
            ("validated-one", "validated"),
        )
        pattern_id = cursor.lastrowid
        migrated_conn.commit()

        migrated_conn.execute(
            "UPDATE learned_patterns SET confidence = 0.77 WHERE id = ?",
            (pattern_id,),
        )
        row = migrated_conn.execute(
            "SELECT confidence FROM learned_patterns WHERE id = ?",
            (pattern_id,),
        ).fetchone()
        assert abs(row[0] - 0.77) < 1e-6

    def test_is_pattern_protected_true_for_locked(self, migrated_conn: sqlite3.Connection) -> None:
        cursor = migrated_conn.execute(
            "INSERT INTO learned_patterns (pattern, trust_tier) VALUES (?, ?)",
            ("p-locked", "locked"),
        )
        migrated_conn.commit()
        assert is_pattern_protected(migrated_conn, cursor.lastrowid) is True

    def test_is_pattern_protected_false_for_volatile(
        self, migrated_conn: sqlite3.Connection
    ) -> None:
        cursor = migrated_conn.execute(
            "INSERT INTO learned_patterns (pattern) VALUES (?)",
            ("p-vol",),
        )
        migrated_conn.commit()
        assert is_pattern_protected(migrated_conn, cursor.lastrowid) is False

    def test_is_pattern_protected_false_for_missing(
        self, migrated_conn: sqlite3.Connection
    ) -> None:
        assert is_pattern_protected(migrated_conn, 9_999_999) is False

    def test_is_pattern_protected_false_on_pre_v7(self, fresh_conn: sqlite3.Connection) -> None:
        """Pre-v7 DB has no trust_tier column — helper returns False, not error."""
        assert is_pattern_protected(fresh_conn, 1) is False

    def test_memory_audit_append_only_blocks_update(
        self, migrated_conn: sqlite3.Connection
    ) -> None:
        cursor = migrated_conn.execute(
            "INSERT INTO memory_audit (actor, action, source_table) VALUES (?, ?, ?)",
            ("test", "insert", "learned_patterns"),
        )
        audit_id = cursor.lastrowid
        migrated_conn.commit()

        with pytest.raises(sqlite3.IntegrityError):
            migrated_conn.execute(
                "UPDATE memory_audit SET actor = 'tampered' WHERE id = ?",
                (audit_id,),
            )

    def test_memory_audit_append_only_blocks_delete(
        self, migrated_conn: sqlite3.Connection
    ) -> None:
        cursor = migrated_conn.execute(
            "INSERT INTO memory_audit (actor, action, source_table) VALUES (?, ?, ?)",
            ("test", "insert", "observations"),
        )
        audit_id = cursor.lastrowid
        migrated_conn.commit()

        with pytest.raises(sqlite3.IntegrityError):
            migrated_conn.execute("DELETE FROM memory_audit WHERE id = ?", (audit_id,))

    def test_record_audit_helper_inserts_row(self, migrated_conn: sqlite3.Connection) -> None:
        audit_id = record_audit(
            migrated_conn,
            actor="unit-test",
            action="reject",
            source_table="learned_patterns",
            source_id=42,
            reason="injection_pattern_matched:0",
        )
        assert audit_id is not None and audit_id > 0

        row = migrated_conn.execute(
            "SELECT actor, action, source_table, source_id, reason FROM memory_audit WHERE id = ?",
            (audit_id,),
        ).fetchone()
        assert row["actor"] == "unit-test"
        assert row["action"] == "reject"
        assert row["source_table"] == "learned_patterns"
        assert row["source_id"] == 42
        assert row["reason"] == "injection_pattern_matched:0"

    def test_record_audit_returns_none_on_pre_v7(self, fresh_conn: sqlite3.Connection) -> None:
        """record_audit must silently no-op on pre-v7 DBs — never raise."""
        result = record_audit(
            fresh_conn,
            actor="test",
            action="insert",
            source_table="learned_patterns",
        )
        assert result is None

    def test_memory_audit_in_db_stats(self, migrated_conn: sqlite3.Connection) -> None:
        stats = get_db_stats(migrated_conn)
        assert "memory_audit" in stats["tables"]
        assert stats["tables"]["memory_audit"] == 0

    def test_v7_idempotent(self, fresh_conn: sqlite3.Connection) -> None:
        """Re-running migrations must not duplicate columns or triggers."""
        run_migrations(fresh_conn)
        run_migrations(fresh_conn)
        assert has_memory_audit_table(fresh_conn) is True
        assert get_schema_version(fresh_conn) >= 7

    def test_constants_exported(self) -> None:
        """The sanitizer depends on these sets — contract test."""
        assert "volatile" in VALID_TRUST_TIERS
        assert "validated" in VALID_TRUST_TIERS
        assert "locked" in VALID_TRUST_TIERS
        assert "core" in VALID_TRUST_TIERS
        assert "locked" in PROTECTED_TRUST_TIERS
        assert "core" in PROTECTED_TRUST_TIERS
        assert "volatile" not in PROTECTED_TRUST_TIERS
        assert "agent_self" in VALID_PROVENANCE
        assert "user_directive" in VALID_PROVENANCE
        assert "extracted_from_outcome" in VALID_PROVENANCE
        assert "promoted_from_rule" in VALID_PROVENANCE
        assert "imported" in VALID_PROVENANCE


# ---------------------------------------------------------------------------
# Migration v8 — Validation Throttle (pattern_validations)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Migration v9 — FTS5 over document_chunks
# ---------------------------------------------------------------------------


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


def test_find_project_root_prefers_marker_over_stray(tmp_path: Path) -> None:
    """TASK-047: a subdir holding a STRAY .coding-os must resolve to the
    marker-co-located project root, not the stray."""
    from database import _find_project_root_from_cwd

    root = tmp_path / "proj"
    (root / ".coding-os").mkdir(parents=True)
    (root / ".git").mkdir()  # root marker
    sub = root / "src" / "cli"
    (sub / ".coding-os").mkdir(parents=True)  # stray, NO marker sibling
    assert _find_project_root_from_cwd(sub).resolve() == root.resolve()


def test_find_project_root_falls_back_to_innermost_without_marker(
    tmp_path: Path,
) -> None:
    """No marker anywhere → innermost .coding-os (TASK-117 anti-lazy-create)."""
    from database import _find_project_root_from_cwd

    root = tmp_path / "bare"
    (root / ".coding-os").mkdir(parents=True)
    sub = root / "deep"
    (sub / ".coding-os").mkdir(parents=True)
    assert _find_project_root_from_cwd(sub).resolve() == sub.resolve()


# ---------------------------------------------------------------------------
# Migration v35 — scale foundation (TASK-226)
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
            "SELECT task_id FROM tasks WHERE status = ? "
            "ORDER BY completed_at DESC LIMIT 10",
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

    def test_trigger_maintains_junction_on_insert(
        self, migrated_conn: sqlite3.Connection
    ) -> None:
        _seed_task(
            migrated_conn, "TASK-902", dependencies='["TASK-1", "TASK-2"]'
        )
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


class TestV36ScrubUsername:
    """v36 backfill strips the local username from historical observations
    (files_modified + title) — the PII the on-disk corpus leaked pre-fix."""

    def test_backfill_scrubs_root_and_home(self, tmp_path: Path) -> None:
        import os

        from database import _migrate_v36_scrub_username_from_observations

        db = tmp_path / ".coding-os" / "coding-os.db"
        db.parent.mkdir(parents=True)
        conn = init_db(db)
        root, home = str(tmp_path), os.path.expanduser("~")
        conn.execute(
            "INSERT INTO observations (session_id,tool_name,observation_type,memory_type,"
            "impact_score,title,narrative,files_modified,content_hash) "
            "VALUES ('s','Edit','edit','discovery',0.5,?,?,?, 'h1')",
            (f"Modified {root}/src/a.py", "n", f"{root}/src/a.py"),
        )
        conn.execute(
            "INSERT INTO observations (session_id,tool_name,observation_type,memory_type,"
            "impact_score,title,narrative,files_modified,content_hash) "
            "VALUES ('s','Edit','edit','discovery',0.5,?,?,?, 'h2')",
            (f"Modified {home}/x/b.py", "n", f"{home}/x/b.py"),
        )
        conn.commit()

        _migrate_v36_scrub_username_from_observations(conn)

        rows = conn.execute(
            "SELECT title, files_modified FROM observations ORDER BY content_hash"
        ).fetchall()
        conn.close()
        assert rows[0][1] == "src/a.py" and rows[0][0] == "Modified src/a.py"
        assert rows[1][1] == "~/x/b.py"
        for title, fm in rows:  # no row leaks the absolute root or home prefix
            assert root + "/" not in (title or "") and root + "/" not in (fm or "")
            assert home + "/" not in (fm or "")

    def test_backfill_idempotent(self, tmp_path: Path) -> None:
        from database import _migrate_v36_scrub_username_from_observations

        db = tmp_path / ".coding-os" / "coding-os.db"
        db.parent.mkdir(parents=True)
        conn = init_db(db)
        conn.execute(
            "INSERT INTO observations (session_id,tool_name,observation_type,memory_type,"
            "impact_score,title,narrative,files_modified,content_hash) "
            "VALUES ('s','Edit','edit','discovery',0.5,?,?,?, 'h1')",
            (f"Modified {tmp_path}/src/a.py", "n", f"{tmp_path}/src/a.py"),
        )
        conn.commit()
        _migrate_v36_scrub_username_from_observations(conn)
        first = conn.execute("SELECT files_modified FROM observations").fetchone()[0]
        _migrate_v36_scrub_username_from_observations(conn)  # second run = no-op
        second = conn.execute("SELECT files_modified FROM observations").fetchone()[0]
        conn.close()
        assert first == second == "src/a.py"
