"""
Stress tests for the thinking_os memory system (TASK-141-146).

Simulates different states, edge cases, concurrent patterns, and
multi-persona scenarios to find bugs.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import get_schema_version, has_fts5_table, init_db
from tools.learning import learn_extract, learn_validate
from tools.metrics import metric_query, metric_record
from tools.routing import route_model


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    c = init_db(tmp_path / "test.db")
    yield c
    c.close()


# ===========================================================================
# Persona 1: New User — Empty DB, First Day
# ===========================================================================


class TestPersonaConcurrent:
    """Test WAL mode enables concurrent reads during writes."""

    def test_wal_mode_active(self, conn):
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "wal"

    def test_concurrent_reads_during_insert(self, conn, tmp_path):
        """Simulate concurrent read while writing."""
        db_path = tmp_path / "concurrent.db"
        conn1 = init_db(db_path)
        conn2 = init_db(db_path)

        try:
            # Write with conn1
            conn1.execute("INSERT INTO observations (title) VALUES (?)", ("Write test",))
            conn1.commit()

            # Read with conn2 should work (WAL allows concurrent read)
            row = conn2.execute("SELECT COUNT(*) FROM observations").fetchone()
            assert row[0] >= 1
        finally:
            conn1.close()
            conn2.close()


class TestPersonaDataIntegrity:
    """Verify data integrity across operations."""

    def test_validate_then_suggest_consistency(self, conn):
        """Validate pattern, then check suggest reflects new confidence."""
        conn.execute(
            "INSERT INTO learned_patterns (pattern, domain, confidence, times_validated) "
            "VALUES (?, ?, ?, ?)",
            ("Consistency test", "BACKEND", 0.5, 1),
        )
        conn.commit()
        pid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        learn_validate(conn, pattern_id=pid, was_helpful=True)
        row = conn.execute(
            "SELECT confidence FROM learned_patterns WHERE id = ?", (pid,)
        ).fetchone()
        assert row[0] > 0.5

    def test_extract_then_validate_workflow(self, conn):
        """Full workflow: seed data → extract → validate → check."""
        for i in range(10):
            conn.execute(
                "INSERT INTO task_outcomes (task_id, type, domain, complexity, outcome) "
                "VALUES (?, ?, ?, ?, ?)",
                (f"TASK-{i}", "feat", "BACKEND", "CLEAR", "rework" if i < 6 else "success"),
            )
        conn.commit()

        # Extract
        result = learn_extract(conn, min_occurrences=3)
        assert result["status"] == "ok"
        assert len(result["extracted"]) > 0

        # Validate first extracted pattern
        pid = result["extracted"][0]["id"]
        v_result = learn_validate(conn, pattern_id=pid, was_helpful=True)
        assert v_result["new_confidence"] > v_result["old_confidence"]

    def test_metric_record_then_query_consistency(self, conn):
        """Record metrics, verify query returns them."""
        metric_record(
            conn, task_id="TASK-50", agent_type="general", outcome="success", domain="BACKEND"
        )
        metric_record(
            conn, task_id="TASK-51", agent_type="general", outcome="rework", domain="BACKEND"
        )

        result = metric_query(conn, domain="BACKEND")
        assert result["total"] == 2
        outcomes = {r["outcome"] for r in result["rows"]}
        assert outcomes == {"success", "rework"}


class TestPersonaMigration:
    """Test migration scenarios."""

    def test_fresh_db_gets_all_migrations(self, tmp_path):
        conn = init_db(tmp_path / "fresh.db")
        try:
            assert get_schema_version(conn) >= 2
        finally:
            conn.close()

    def test_reopen_db_no_migration_needed(self, tmp_path):
        db_path = tmp_path / "reopen.db"
        conn1 = init_db(db_path)
        conn1.close()

        conn2 = init_db(db_path)
        try:
            assert get_schema_version(conn2) >= 2
            # Data should persist
            conn2.execute("INSERT INTO observations (title) VALUES (?)", ("Persist test",))
            conn2.commit()
        finally:
            conn2.close()

        conn3 = init_db(db_path)
        try:
            row = conn3.execute(
                "SELECT COUNT(*) FROM observations WHERE title = 'Persist test'"
            ).fetchone()
            assert row[0] == 1
        finally:
            conn3.close()


class TestPersonaFTS5Stress:
    """Stress test FTS5 with various inputs."""

    def test_fts5_with_special_characters(self, conn):
        if not has_fts5_table(conn):
            pytest.skip("FTS5 not available")
        conn.execute(
            "INSERT INTO observations (title, narrative, concepts) VALUES (?, ?, ?)",
            ("Special: @#$%^&*()", "Narrative with <html> tags & entities", '["special"]'),
        )
        conn.commit()
        # Should not crash
        results = conn.execute(
            "SELECT * FROM observations_fts WHERE observations_fts MATCH 'special'",
        ).fetchall()
        assert len(results) >= 1

    def test_fts5_with_empty_fields(self, conn):
        if not has_fts5_table(conn):
            pytest.skip("FTS5 not available")
        conn.execute(
            "INSERT INTO observations (title, narrative, concepts) VALUES (?, ?, ?)",
            (None, None, None),
        )
        conn.commit()
        # Should not crash the FTS trigger
        count = conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
        assert count >= 1

    def test_fts5_bulk_insert(self, conn):
        if not has_fts5_table(conn):
            pytest.skip("FTS5 not available")
        for i in range(100):
            conn.execute(
                "INSERT INTO observations (title, narrative, concepts) VALUES (?, ?, ?)",
                (f"Bulk {i}", f"Bulk narrative {i}", f'["bulk","item{i}"]'),
            )
        conn.commit()
        results = conn.execute(
            "SELECT COUNT(*) FROM observations_fts WHERE observations_fts MATCH 'bulk'",
        ).fetchone()
        assert results[0] == 100


class TestPersonaConfidenceDecay:
    """Test confidence behavior over multiple operations."""

    def test_repeated_validation_converges(self, conn):
        conn.execute(
            "INSERT INTO learned_patterns (pattern, confidence) VALUES (?, ?)",
            ("Convergence test", 0.5),
        )
        conn.commit()
        pid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Validate 20 times
        for _ in range(20):
            learn_validate(conn, pattern_id=pid, was_helpful=True)

        row = conn.execute(
            "SELECT confidence FROM learned_patterns WHERE id = ?", (pid,)
        ).fetchone()
        # Should converge near 0.95 but never exceed
        assert row[0] <= 0.95

    def test_repeated_violation_reaches_floor(self, conn):
        conn.execute(
            "INSERT INTO learned_patterns (pattern, confidence) VALUES (?, ?)",
            ("Floor test", 0.9),
        )
        conn.commit()
        pid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        for _ in range(50):
            learn_validate(conn, pattern_id=pid, was_helpful=False)

        row = conn.execute(
            "SELECT confidence FROM learned_patterns WHERE id = ?", (pid,)
        ).fetchone()
        assert row[0] >= 0.1

    def test_alternating_validation(self, conn):
        conn.execute(
            "INSERT INTO learned_patterns (pattern, confidence) VALUES (?, ?)",
            ("Alternating test", 0.5),
        )
        conn.commit()
        pid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        for i in range(20):
            learn_validate(conn, pattern_id=pid, was_helpful=(i % 2 == 0))

        row = conn.execute(
            "SELECT confidence FROM learned_patterns WHERE id = ?", (pid,)
        ).fetchone()
        # Should stay roughly stable
        assert 0.1 <= row[0] <= 0.95


class TestPersonaRoutingEdges:
    """Test routing with unusual data distributions."""

    def test_all_rework_domain(self, conn):
        """Domain with 100% rework rate."""
        for i in range(15):
            conn.execute(
                "INSERT INTO task_outcomes (task_id, type, domain, complexity, outcome, model) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (f"TASK-{i}", "feat", "BROKEN", "CLEAR", "rework", "sonnet"),
            )
        conn.commit()
        result = route_model(conn, complexity="CLEAR", domain="BROKEN")
        # Should still return something, not crash
        assert "recommended_model" in result

    def test_single_model_only(self, conn):
        """Only one model used."""
        for i in range(20):
            conn.execute(
                "INSERT INTO task_outcomes (task_id, type, domain, complexity, outcome, model) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (f"TASK-{i}", "feat", "MONO", "COMPLICATED", "success", "opus"),
            )
        conn.commit()
        result = route_model(conn, complexity="COMPLICATED", domain="MONO")
        assert result["recommended_model"] == "opus"
