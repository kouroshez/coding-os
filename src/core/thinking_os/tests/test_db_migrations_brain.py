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
    PROTECTED_TRUST_TIERS,
    VALID_PROVENANCE,
    VALID_TRUST_TIERS,
    get_connection,
    get_db_stats,
    get_schema_version,
    has_memory_audit_table,
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
