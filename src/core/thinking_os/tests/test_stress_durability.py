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
