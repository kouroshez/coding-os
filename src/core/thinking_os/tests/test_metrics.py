"""
Tests for MCP metrics tools (TASK-143).

Covers cos_metric_record, cos_metric_query, cos_metric_trend,
and empty DB handling.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import init_db
from tools.metrics import metric_query, metric_record, metric_trend


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    """Fully migrated DB connection."""
    c = init_db(tmp_path / "test.db")
    yield c
    c.close()


@pytest.fixture
def seeded_conn(conn: sqlite3.Connection) -> sqlite3.Connection:
    """DB with sample metrics."""
    records = [
        ("TASK-100", "general", "sonnet", 30000, "success", "BACKEND", "CLEAR"),
        ("TASK-101", "planner", "opus", 60000, "success", "BACKEND", "COMPLICATED"),
        ("TASK-102", "general", "sonnet", 45000, "rework", "FRONTEND", "CLEAR"),
        ("TASK-103", "code-reviewer", "sonnet", 15000, "success", "FRONTEND", "CLEAR"),
        ("TASK-104", "general", "haiku", 10000, "blocked", "INFRA", "COMPLEX"),
        ("TASK-105", "general", "sonnet", 20000, "success", "BACKEND", "CLEAR"),
        ("TASK-106", "planner", "opus", 55000, "rework", "BACKEND", "COMPLICATED"),
    ]
    for task_id, agent, model, dur, outcome, domain, complexity in records:
        metric_record(
            conn,
            task_id=task_id,
            agent_type=agent,
            model=model,
            duration_ms=dur,
            outcome=outcome,
            domain=domain,
            complexity=complexity,
        )
    return conn


# ---------------------------------------------------------------------------
# cos_metric_record
# ---------------------------------------------------------------------------

class TestMetricRecord:
    def test_record_returns_id(self, conn: sqlite3.Connection) -> None:
        result = metric_record(
            conn, task_id="TASK-200", agent_type="general",
            model="sonnet", duration_ms=1000, outcome="success",
        )
        assert "id" in result
        assert result["status"] == "recorded"

    def test_record_inserts_row(self, conn: sqlite3.Connection) -> None:
        metric_record(
            conn, task_id="TASK-201", agent_type="planner",
            outcome="success", domain="BACKEND",
        )
        row = conn.execute(
            "SELECT * FROM agent_metrics WHERE task_id = ?", ("TASK-201",)
        ).fetchone()
        assert row is not None
        assert row["agent_type"] == "planner"
        assert row["domain"] == "BACKEND"

    def test_record_invalid_outcome(self, conn: sqlite3.Connection) -> None:
        result = metric_record(
            conn, agent_type="general", outcome="invalid_outcome",
        )
        assert "error" in result

    def test_record_optional_fields_null(self, conn: sqlite3.Connection) -> None:
        result = metric_record(conn, agent_type="general", outcome="success")
        row = conn.execute(
            "SELECT * FROM agent_metrics WHERE id = ?", (result["id"],)
        ).fetchone()
        assert row["task_id"] is None
        assert row["model"] is None
        assert row["duration_ms"] is None

    def test_record_multiple(self, conn: sqlite3.Connection) -> None:
        for i in range(5):
            metric_record(conn, agent_type="general", outcome="success")
        count = conn.execute("SELECT COUNT(*) FROM agent_metrics").fetchone()[0]
        assert count == 5


# ---------------------------------------------------------------------------
# cos_metric_query
# ---------------------------------------------------------------------------

class TestMetricQuery:
    def test_empty_db_returns_empty(self, conn: sqlite3.Connection) -> None:
        result = metric_query(conn)
        assert result["total"] == 0
        assert result["rows"] == []

    def test_no_filters_returns_all(self, seeded_conn: sqlite3.Connection) -> None:
        result = metric_query(seeded_conn)
        assert result["total"] == 7
        assert result["count"] == 7

    def test_filter_by_domain(self, seeded_conn: sqlite3.Connection) -> None:
        result = metric_query(seeded_conn, domain="BACKEND")
        assert result["total"] == 4
        for row in result["rows"]:
            assert row["domain"] == "BACKEND"

    def test_filter_by_outcome(self, seeded_conn: sqlite3.Connection) -> None:
        result = metric_query(seeded_conn, outcome="rework")
        assert result["total"] == 2
        for row in result["rows"]:
            assert row["outcome"] == "rework"

    def test_filter_by_model(self, seeded_conn: sqlite3.Connection) -> None:
        result = metric_query(seeded_conn, model="opus")
        assert result["total"] == 2

    def test_filter_by_agent_type(self, seeded_conn: sqlite3.Connection) -> None:
        result = metric_query(seeded_conn, agent_type="planner")
        assert result["total"] == 2

    def test_combined_filters(self, seeded_conn: sqlite3.Connection) -> None:
        result = metric_query(seeded_conn, domain="BACKEND", outcome="success")
        assert result["total"] == 3

    def test_limit(self, seeded_conn: sqlite3.Connection) -> None:
        result = metric_query(seeded_conn, limit=3)
        assert result["total"] == 7
        assert result["count"] == 3

    def test_limit_clamped(self, seeded_conn: sqlite3.Connection) -> None:
        result = metric_query(seeded_conn, limit=200)
        assert result["count"] == 7  # only 7 rows, clamped to 100 but only 7 exist

    def test_sorted_by_date_desc(self, seeded_conn: sqlite3.Connection) -> None:
        result = metric_query(seeded_conn)
        dates = [row["created_at"] for row in result["rows"]]
        assert dates == sorted(dates, reverse=True)


# ---------------------------------------------------------------------------
# cos_metric_trend
# ---------------------------------------------------------------------------

class TestMetricTrend:
    def test_empty_db_returns_empty_trends(self, conn: sqlite3.Connection) -> None:
        result = metric_trend(conn)
        assert result["trends"] == []

    def test_success_rate_by_domain(self, seeded_conn: sqlite3.Connection) -> None:
        result = metric_trend(seeded_conn, metric="success_rate", group_by="domain")
        assert result["metric"] == "success_rate"
        assert result["group_by"] == "domain"
        assert len(result["trends"]) > 0
        for entry in result["trends"]:
            assert "rate" in entry
            assert 0 <= entry["rate"] <= 1

    def test_rework_rate(self, seeded_conn: sqlite3.Connection) -> None:
        result = metric_trend(seeded_conn, metric="rework_rate", group_by="domain")
        assert result["metric"] == "rework_rate"

    def test_count_metric(self, seeded_conn: sqlite3.Connection) -> None:
        result = metric_trend(seeded_conn, metric="count", group_by="domain")
        total = sum(e["rate"] for e in result["trends"])
        assert total == 7

    def test_group_by_model(self, seeded_conn: sqlite3.Connection) -> None:
        result = metric_trend(seeded_conn, group_by="model")
        group_keys = {e["group_key"] for e in result["trends"]}
        assert "sonnet" in group_keys

    def test_invalid_metric(self, seeded_conn: sqlite3.Connection) -> None:
        result = metric_trend(seeded_conn, metric="invalid")
        assert "error" in result

    def test_invalid_group_by(self, seeded_conn: sqlite3.Connection) -> None:
        result = metric_trend(seeded_conn, group_by="invalid")
        assert "error" in result

    def test_window_days_clamped(self, seeded_conn: sqlite3.Connection) -> None:
        result = metric_trend(seeded_conn, window_days=500)
        assert result["window_days"] == 365
