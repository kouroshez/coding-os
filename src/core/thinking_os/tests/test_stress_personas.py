"""
Stress tests for the thinking_os memory system (TASK-141-146).

Simulates different states, edge cases, concurrent patterns, and
multi-persona scenarios to find bugs.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import get_db_stats, has_fts5_table, init_db
from tools.learning import learn_extract, learn_suggest, learn_validate
from tools.memory import memory_details, memory_promote, memory_search, memory_timeline
from tools.metrics import metric_query, metric_record, metric_trend
from tools.routing import route_model, route_skill


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    c = init_db(tmp_path / "test.db")
    yield c
    c.close()


# ===========================================================================
# Persona 1: New User — Empty DB, First Day
# ===========================================================================


class TestPersonaNewUser:
    """First-day user with completely empty DB."""

    def test_health_on_empty_db(self, conn):
        stats = get_db_stats(conn)
        assert all(v == 0 for v in stats["tables"].values())

    def test_search_empty(self, conn):
        result = memory_search(conn, query="anything")
        assert result["count"] == 0

    def test_timeline_empty(self, conn):
        result = memory_timeline(conn, days=30)
        assert result["count"] == 0

    def test_extract_insufficient(self, conn):
        result = learn_extract(conn)
        assert result["status"] == "insufficient_data"

    def test_suggest_empty(self, conn):
        result = learn_suggest(conn, domain="BACKEND")
        assert result["suggestions"] == []

    def test_route_model_cold(self, conn):
        result = route_model(conn, complexity="CLEAR")
        assert result["confidence"] == 0.0

    def test_route_skill_cold(self, conn):
        result = route_skill(conn, domain="BACKEND")
        assert result["fallback_source"] == "skill-enforcement.md"

    def test_metric_query_empty(self, conn):
        result = metric_query(conn)
        assert result["total"] == 0

    def test_metric_trend_empty(self, conn):
        result = metric_trend(conn)
        assert result["trends"] == []

    def test_details_not_found(self, conn):
        result = memory_details(conn, pattern_id=1, source="learned_patterns")
        assert "error" in result


class TestPersonaPowerUser:
    """User with 200+ tasks and lots of observations."""

    @pytest.fixture
    def heavy_conn(self, conn):
        # Insert 200 task outcomes
        for i in range(200):
            domain = ["BACKEND", "FRONTEND", "INFRA"][i % 3]
            outcome = ["success", "success", "success", "rework"][i % 4]
            model = ["sonnet", "opus", "haiku"][i % 3]
            complexity = ["CLEAR", "COMPLICATED", "COMPLEX"][i % 3]
            conn.execute(
                "INSERT INTO task_outcomes (task_id, type, domain, complexity, outcome, model, skills_used) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    f"TASK-{i}",
                    "feat",
                    domain,
                    complexity,
                    outcome,
                    model,
                    f"skill-{domain.lower()}",
                ),
            )

        # Insert 500 observations
        for i in range(500):
            conn.execute(
                "INSERT INTO observations (session_id, tool_name, title, narrative, "
                "memory_type, impact_score, concepts) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    f"sess-{i // 10}",
                    "Read",
                    f"Observation {i}",
                    f"Narrative for observation {i} about {'Django' if i % 3 == 0 else 'React'}",
                    "discovery",
                    0.5 + (i % 5) * 0.1,
                    json.dumps(["obs", f"topic{i % 10}"]),
                ),
            )

        # Insert 50 learned patterns
        for i in range(50):
            domain = ["BACKEND", "FRONTEND", "INFRA"][i % 3]
            conn.execute(
                "INSERT INTO learned_patterns (pattern, memory_type, domain, confidence, "
                "impact_score, concepts, times_validated, access_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    f"Pattern {i}: {domain} best practice",
                    "pattern",
                    domain,
                    0.3 + (i % 7) * 0.1,
                    0.5,
                    json.dumps([domain.lower(), f"p{i}"]),
                    i % 10,
                    i % 15,
                ),
            )

        conn.commit()
        return conn

    def test_search_performance(self, heavy_conn):
        result = memory_search(heavy_conn, query="Django", use_fts5=has_fts5_table(heavy_conn))
        assert result["count"] > 0
        assert result["count"] <= 5

    def test_search_like_fallback_performance(self, heavy_conn):
        result = memory_search(heavy_conn, query="Django", use_fts5=False)
        assert result["count"] > 0

    def test_timeline_with_200_tasks(self, heavy_conn):
        result = memory_timeline(heavy_conn, days=365, limit=50)
        assert result["count"] <= 50

    def test_extract_from_200_tasks(self, heavy_conn):
        result = learn_extract(heavy_conn, min_occurrences=10)
        assert result["status"] == "ok"
        assert result["total_outcomes_analyzed"] == 200

    def test_suggest_from_50_patterns(self, heavy_conn):
        result = learn_suggest(heavy_conn, domain="BACKEND", limit=10)
        assert result["count"] <= 10

    def test_route_model_warm(self, heavy_conn):
        result = route_model(heavy_conn, complexity="COMPLICATED", domain="BACKEND")
        # With 200 tasks, data_points should be high
        assert result["data_points"] == 200
        # May or may not have enough per-bucket data for confidence > 0
        assert "recommended_model" in result

    def test_metric_trend_200_tasks(self, heavy_conn):
        for i in range(200):
            metric_record(
                heavy_conn,
                agent_type="general",
                outcome=["success", "rework"][i % 2],
                domain=["BACKEND", "FRONTEND"][i % 2],
            )
        result = metric_trend(heavy_conn, metric="success_rate", group_by="domain")
        assert len(result["trends"]) > 0

    def test_stats_with_heavy_data(self, heavy_conn):
        stats = get_db_stats(heavy_conn)
        assert stats["tables"]["task_outcomes"] == 200
        assert stats["tables"]["observations"] == 500
        assert stats["tables"]["learned_patterns"] == 50


class TestPersonaSecurityTester:
    """Attempts SQL injection and malicious inputs."""

    def test_search_sql_injection(self, conn):
        result = memory_search(conn, query="'; DROP TABLE observations; --")
        # Should not crash, DB should be intact
        assert "results" in result
        tables = [
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        ]
        assert "observations" in tables

    def test_metric_record_injection(self, conn):
        result = metric_record(
            conn,
            agent_type="'; DROP TABLE agent_metrics; --",
            outcome="success",
        )
        assert result["status"] == "recorded"
        tables = [
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        ]
        assert "agent_metrics" in tables

    def test_search_with_null_bytes(self, conn):
        result = memory_search(conn, query="test\x00injection")
        assert "results" in result

    def test_very_long_query(self, conn):
        result = memory_search(conn, query="x" * 10000)
        assert "results" in result

    def test_unicode_in_patterns(self, conn):
        conn.execute(
            "INSERT INTO learned_patterns (pattern, confidence) VALUES (?, ?)",
            ("使用サービス层进行数据库写入 🧠", 0.5),
        )
        conn.commit()
        result = memory_search(conn, query="サービス", use_fts5=False)
        assert "results" in result

    def test_metric_record_invalid_outcome_no_crash(self, conn):
        result = metric_record(conn, agent_type="test", outcome="invalid")
        assert "error" in result


class TestPersonaEdgeCases:
    """Tests boundary values and unusual states."""

    def test_confidence_exact_floor(self, conn):
        conn.execute(
            "INSERT INTO learned_patterns (pattern, confidence) VALUES (?, ?)",
            ("Floor pattern", 0.1),
        )
        conn.commit()
        pid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        result = learn_validate(conn, pattern_id=pid, was_helpful=False)
        assert result["new_confidence"] >= 0.1

    def test_confidence_exact_ceiling(self, conn):
        conn.execute(
            "INSERT INTO learned_patterns (pattern, confidence) VALUES (?, ?)",
            ("Ceiling pattern", 0.95),
        )
        conn.commit()
        pid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        result = learn_validate(conn, pattern_id=pid, was_helpful=True)
        assert result["new_confidence"] <= 0.95

    def test_promote_at_exact_threshold(self, conn):
        conn.execute(
            "INSERT INTO learned_patterns (pattern, confidence, domain) VALUES (?, ?, ?)",
            ("Threshold pattern", 0.3, "BACKEND"),
        )
        conn.commit()
        pid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        result = memory_promote(conn, pattern_id=pid, target="feedback", memory_dir="/tmp")
        assert result["status"] == "promoted"

    def test_promote_below_threshold(self, conn):
        conn.execute(
            "INSERT INTO learned_patterns (pattern, confidence) VALUES (?, ?)",
            ("Below threshold", 0.29),
        )
        conn.commit()
        pid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        result = memory_promote(conn, pattern_id=pid, target="feedback", memory_dir="/tmp")
        assert "error" in result

    def test_metric_limit_zero(self, conn):
        result = metric_query(conn, limit=0)
        # Should clamp to 1
        assert "rows" in result

    def test_metric_limit_negative(self, conn):
        result = metric_query(conn, limit=-5)
        assert "rows" in result

    def test_timeline_zero_days(self, conn):
        result = memory_timeline(conn, days=0)
        assert result["days"] == 1  # clamped

    def test_search_limit_zero(self, conn):
        result = memory_search(conn, query="test", limit=0)
        assert result["count"] == 0  # clamped to 1 but no results

    def test_observation_with_null_fields(self, conn):
        conn.execute("INSERT INTO observations (title) VALUES (?)", ("Minimal",))
        conn.commit()
        result = memory_timeline(conn, days=365)
        assert result["count"] >= 0  # should not crash

    def test_details_with_string_id_for_task(self, conn):
        conn.execute(
            "INSERT INTO task_outcomes (task_id, type, domain, complexity, outcome) "
            "VALUES (?, ?, ?, ?, ?)",
            ("TASK-999", "feat", "BACKEND", "CLEAR", "success"),
        )
        conn.commit()
        result = memory_details(conn, pattern_id="TASK-999", source="task_outcomes")
        assert "record" in result
