"""Seed simulation — the learning loop, metrics, and routing over the seeded corpus.

Corpus generators live in tests/seed_corpus.py.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.metrics import metric_query, metric_record, metric_trend
from tools.routing import route_model, route_skill

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


class TestMetrics:
    """Test metric recording and querying."""

    def test_query_by_domain(self, seeded_conn: sqlite3.Connection):
        result = metric_query(seeded_conn, domain="BACKEND")
        assert result["total"] > 0

    def test_query_by_model(self, seeded_conn: sqlite3.Connection):
        result = metric_query(seeded_conn, model="opus")
        assert result["total"] >= 0

    def test_query_by_outcome(self, seeded_conn: sqlite3.Connection):
        result = metric_query(seeded_conn, outcome="rework")
        assert result["total"] >= 0

    def test_query_by_date_range(self, seeded_conn: sqlite3.Connection):
        result = metric_query(
            seeded_conn,
            date_from="2026-01-01",
            date_to="2026-12-31",
        )
        assert result["total"] > 0

    def test_trend_by_domain(self, seeded_conn: sqlite3.Connection):
        result = metric_trend(
            seeded_conn, metric="success_rate", group_by="domain", window_days=365
        )
        assert len(result["trends"]) > 0

    def test_trend_by_model(self, seeded_conn: sqlite3.Connection):
        result = metric_trend(seeded_conn, metric="success_rate", group_by="model", window_days=365)
        assert len(result["trends"]) > 0

    def test_trend_rework_rate(self, seeded_conn: sqlite3.Connection):
        result = metric_trend(seeded_conn, metric="rework_rate", group_by="domain", window_days=365)
        assert "trends" in result

    def test_record_new_metric(self, seeded_conn: sqlite3.Connection):
        result = metric_record(
            seeded_conn,
            agent_type="tdd-guide",
            outcome="success",
            task_id="TASK-NEW",
            model="opus",
            domain="BACKEND",
            complexity="COMPLICATED",
        )
        assert result["status"] == "recorded"


class TestRouting:
    """Test model and skill routing with seeded data."""

    def test_route_model_with_data(self, seeded_conn: sqlite3.Connection):
        result = route_model(seeded_conn, complexity="COMPLICATED", domain="BACKEND")
        assert "recommended_model" in result
        assert result["data_points"] > 0

    def test_route_model_clear(self, seeded_conn: sqlite3.Connection):
        result = route_model(seeded_conn, complexity="CLEAR", domain="FRONTEND")
        assert "recommended_model" in result

    def test_route_model_complex(self, seeded_conn: sqlite3.Connection):
        result = route_model(seeded_conn, complexity="COMPLEX", domain="BACKEND")
        assert "recommended_model" in result

    def test_route_skill_backend(self, seeded_conn: sqlite3.Connection):
        result = route_skill(seeded_conn, domain="BACKEND", task_type="feat")
        assert len(result["skills"]) > 0

    def test_route_skill_frontend(self, seeded_conn: sqlite3.Connection):
        result = route_skill(seeded_conn, domain="FRONTEND", task_type="fix")
        assert len(result["skills"]) > 0

    def test_route_skill_unknown_domain(self, seeded_conn: sqlite3.Connection):
        result = route_skill(seeded_conn, domain="UNKNOWN")
        assert "skills" in result
