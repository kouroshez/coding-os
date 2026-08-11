"""Seed simulation — the learning loop, metrics, and routing over the seeded corpus.

Corpus generators live in tests/seed_corpus.py.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.seed_corpus import (  # noqa: F401 — pytest resolves fixtures by name
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
from tools.learning import learn_extract, learn_suggest, learn_validate
from tools.memory import memory_details
from tools.metrics import metric_query, metric_record, metric_trend
from tools.routing import route_model, route_skill


class TestLearningCycle:
    """Test the full extract → suggest → validate cycle."""

    def test_extract_finds_patterns(self, seeded_conn: sqlite3.Connection):
        result = learn_extract(seeded_conn, min_occurrences=3)
        assert result["status"] == "ok"
        assert result["total_outcomes_analyzed"] == 200
        assert len(result["extracted"]) > 0, "Should find at least one pattern from 200 outcomes"

    def test_extract_finds_backend_rework(self, seeded_conn: sqlite3.Connection):
        """BACKEND was biased toward rework — extract should catch it."""
        result = learn_extract(seeded_conn, min_occurrences=3)
        patterns = [p["pattern"] for p in result["extracted"]]
        backend_patterns = [p for p in patterns if "BACKEND" in p]
        assert len(backend_patterns) > 0, f"Expected BACKEND rework pattern, got: {patterns}"

    def test_suggest_returns_patterns_after_extract(self, seeded_conn: sqlite3.Connection):
        # First extract
        learn_extract(seeded_conn, min_occurrences=3)
        # Then suggest
        result = learn_suggest(seeded_conn, domain="BACKEND", complexity="COMPLICATED")
        assert result["count"] > 0
        assert result["suggestions"][0]["confidence"] > 0

    def test_suggest_empty_for_unknown_domain(self, seeded_conn: sqlite3.Connection):
        result = learn_suggest(seeded_conn, domain="NONEXISTENT")
        assert result["count"] == 0

    def test_validate_boosts_confidence(self, seeded_conn: sqlite3.Connection):
        learn_extract(seeded_conn, min_occurrences=3)
        suggestions = learn_suggest(seeded_conn, domain="BACKEND")["suggestions"]
        if not suggestions:
            pytest.skip("No patterns to validate")

        pattern_id = suggestions[0]["id"]
        old_conf = suggestions[0]["confidence"]
        result = learn_validate(seeded_conn, pattern_id=pattern_id, was_helpful=True)
        assert result["new_confidence"] > old_conf

    def test_validate_penalizes_confidence(self, seeded_conn: sqlite3.Connection):
        learn_extract(seeded_conn, min_occurrences=3)
        suggestions = learn_suggest(seeded_conn, domain="BACKEND")["suggestions"]
        if not suggestions:
            pytest.skip("No patterns to validate")

        pattern_id = suggestions[0]["id"]
        old_conf = suggestions[0]["confidence"]
        result = learn_validate(seeded_conn, pattern_id=pattern_id, was_helpful=False)
        assert result["new_confidence"] < old_conf

    def test_repeated_validation_has_diminishing_returns(self, seeded_conn: sqlite3.Connection):
        learn_extract(seeded_conn, min_occurrences=3)
        suggestions = learn_suggest(seeded_conn, domain="BACKEND")["suggestions"]
        if not suggestions:
            pytest.skip("No patterns")

        pid = suggestions[0]["id"]
        boosts = []
        for _ in range(10):
            r = learn_validate(seeded_conn, pattern_id=pid, was_helpful=True)
            boosts.append(r["new_confidence"] - r["old_confidence"])

        # Overall trend: later boosts should be smaller than early ones
        # Compare first half average vs second half average
        first_half = sum(boosts[:5]) / 5
        second_half = sum(boosts[5:]) / 5
        assert second_half <= first_half + 0.01, (
            f"Second half avg ({second_half:.4f}) should be <= first half ({first_half:.4f})"
        )

    def test_confidence_never_exceeds_095(self, seeded_conn: sqlite3.Connection):
        learn_extract(seeded_conn, min_occurrences=3)
        suggestions = learn_suggest(seeded_conn, domain="BACKEND")["suggestions"]
        if not suggestions:
            pytest.skip("No patterns")

        pid = suggestions[0]["id"]
        for _ in range(50):
            learn_validate(seeded_conn, pattern_id=pid, was_helpful=True)

        details = memory_details(seeded_conn, pattern_id=pid, source="learned_patterns")
        assert details["record"]["confidence"] <= 0.95

    def test_confidence_never_below_010(self, seeded_conn: sqlite3.Connection):
        learn_extract(seeded_conn, min_occurrences=3)
        suggestions = learn_suggest(seeded_conn, domain="BACKEND")["suggestions"]
        if not suggestions:
            pytest.skip("No patterns")

        pid = suggestions[0]["id"]
        for _ in range(50):
            learn_validate(seeded_conn, pattern_id=pid, was_helpful=False)

        details = memory_details(seeded_conn, pattern_id=pid, source="learned_patterns")
        assert details["record"]["confidence"] >= 0.10


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
