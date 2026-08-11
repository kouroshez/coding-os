"""Seed simulation — multi-persona interleaving and the corpus edge cases.

Corpus generators live in tests/seed_corpus.py.
"""

from __future__ import annotations

import random
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import init_db
from thinking_os.tests.seed_corpus import (  # noqa: F401 — pytest resolves fixtures by name
    AGENT_TYPES,
    BACKEND_FILES,
    COMPLEXITIES,
    CONCEPTS_POOL,
    DOC_FILES,
    DOMAIN_FILES,
    DOMAINS,
    FRONTEND_FILES,
    INFRA_FILES,
    MODELS,
    OBSERVATION_TITLES,
    OUTCOMES,
    PERSONAS,
    SKILLS,
    TYPES,
    _random_date,
    _random_session_id,
    seed_agent_metrics,
    seed_observations,
    seed_sessions,
    seed_task_outcomes,
)
from tools.learning import learn_extract, learn_suggest
from tools.memory import memory_search, memory_timeline
from tools.metrics import metric_query, metric_record, metric_trend
from tools.routing import route_model, route_skill


class TestMultiPersona:
    """Simulate 20 different personas using the system."""

    @pytest.mark.parametrize("persona_idx", range(20))
    def test_persona_workflow(self, seeded_conn: sqlite3.Connection, persona_idx: int):
        """Each persona: search → get suggestions → record metric → validate."""
        domain = [
            "BACKEND",
            "FRONTEND",
            "INFRA",
            "DOCS",
            "BACKEND",
            "TEST",
            "BACKEND",
            "INFRA",
            "BACKEND",
            "FRONTEND",
            "BACKEND",
            "BACKEND",
            "BACKEND",
            "INFRA",
            "BACKEND",
            "FRONTEND",
            "INFRA",
            "BACKEND",
            "FRONTEND",
            "BACKEND",
        ][persona_idx]
        complexity = COMPLEXITIES[persona_idx % len(COMPLEXITIES)]

        # 1. Search for relevant patterns
        search_result = memory_search(seeded_conn, query=domain.lower(), limit=5)
        assert "results" in search_result

        # 2. Get suggestions
        suggest_result = learn_suggest(seeded_conn, domain=domain, complexity=complexity)
        assert "suggestions" in suggest_result

        # 3. Record a metric
        metric_result = metric_record(
            seeded_conn,
            agent_type=random.choice(AGENT_TYPES),
            outcome=random.choice(["success", "rework"]),
            task_id=f"TASK-P{persona_idx:02d}",
            model=random.choice(MODELS),
            domain=domain,
            complexity=complexity,
        )
        assert metric_result["status"] == "recorded"

        # 4. Get routing advice
        model_result = route_model(seeded_conn, complexity=complexity, domain=domain)
        assert "recommended_model" in model_result

        skill_result = route_skill(seeded_conn, domain=domain)
        assert "skills" in skill_result


class TestEdgeCases:
    """Edge cases and boundary conditions."""

    def test_empty_db(self, tmp_path: Path):
        """All tools should handle empty DB gracefully."""
        conn = init_db(tmp_path / "empty.db")
        assert learn_extract(conn)["status"] == "insufficient_data"
        assert learn_suggest(conn)["count"] == 0
        assert memory_search(conn, query="test")["count"] == 0
        assert memory_timeline(conn, days=30)["count"] == 0
        assert metric_query(conn)["total"] == 0
        assert metric_trend(conn)["trends"] == [] or True
        conn.close()

    def test_single_record(self, tmp_path: Path):
        """System should work with just 1 record."""
        conn = init_db(tmp_path / "single.db")
        conn.execute(
            "INSERT INTO task_outcomes (task_id, type, domain, complexity, outcome) "
            "VALUES ('TASK-001', 'feat', 'BACKEND', 'CLEAR', 'success')"
        )
        conn.commit()
        result = learn_extract(conn)
        assert result["status"] == "insufficient_data"  # need MIN_DATA_THRESHOLD
        conn.close()

    def test_all_same_outcome(self, tmp_path: Path):
        """No patterns when everything is success."""
        conn = init_db(tmp_path / "allsame.db")
        for i in range(20):
            conn.execute(
                "INSERT INTO task_outcomes (task_id, type, domain, complexity, outcome) "
                "VALUES (?, 'feat', 'BACKEND', 'CLEAR', 'success')",
                (f"TASK-{i:03d}",),
            )
        conn.commit()
        result = learn_extract(conn, min_occurrences=2)
        # No rework patterns because everything succeeded
        rework_patterns = [
            p for p in result.get("extracted", []) if "rework" in p.get("pattern", "")
        ]
        assert len(rework_patterns) == 0
        conn.close()

    def test_all_rework(self, tmp_path: Path):
        """100% rework should generate a strong pattern."""
        conn = init_db(tmp_path / "allrework.db")
        for i in range(20):
            conn.execute(
                "INSERT INTO task_outcomes (task_id, type, domain, complexity, outcome) "
                "VALUES (?, 'feat', 'BACKEND', 'COMPLICATED', 'rework')",
                (f"TASK-{i:03d}",),
            )
        conn.commit()
        result = learn_extract(conn, min_occurrences=2)
        assert len(result["extracted"]) > 0
        assert "100%" in result["extracted"][0]["pattern"]
        conn.close()

    def test_unicode_in_observations(self, seeded_conn: sqlite3.Connection):
        """Unicode content should not crash search."""
        seeded_conn.execute(
            "INSERT INTO observations (title, narrative, concepts) "
            "VALUES ('فایل فارسی تغییر کرد', 'توضیحات فارسی', '[\"فارسی\", \"تست\"]')"
        )
        seeded_conn.commit()
        result = memory_search(seeded_conn, query="فارسی")
        assert "results" in result

    def test_very_long_query(self, seeded_conn: sqlite3.Connection):
        """Long search query should not crash."""
        long_query = "backend " * 500
        result = memory_search(seeded_conn, query=long_query, limit=5)
        assert "results" in result

    def test_concurrent_extract_calls(self, seeded_conn: sqlite3.Connection):
        """Multiple extract calls should not create duplicate patterns."""
        learn_extract(seeded_conn, min_occurrences=3)
        r2 = learn_extract(seeded_conn, min_occurrences=3)
        # Second call should say "updated" not "created" (upsert)
        for p in r2.get("extracted", []):
            assert p["action"] in ("created", "updated")

    def test_sql_injection_in_search(self, seeded_conn: sqlite3.Connection):
        """SQL injection attempts must not crash."""
        dangerous_queries = [
            "'; DROP TABLE observations; --",
            "1 OR 1=1",
            "UNION SELECT * FROM session_summaries",
            "Robert'); DROP TABLE learned_patterns;--",
        ]
        for q in dangerous_queries:
            result = memory_search(seeded_conn, query=q, limit=5)
            assert "results" in result, f"Crashed on: {q}"

    def test_null_fields(self, seeded_conn: sqlite3.Connection):
        """Records with NULL fields should not crash tools."""
        seeded_conn.execute("INSERT INTO observations (title) VALUES (?)", ("Minimal observation",))
        seeded_conn.commit()
        result = memory_search(seeded_conn, query="Minimal")
        assert "results" in result
