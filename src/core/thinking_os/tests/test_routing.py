"""
Tests for MCP routing tools (TASK-145, TASK-148).

Covers cold start fallback, warm recommendation, sample threshold,
static rules fallback, data-driven suggestions, empty DB,
and routing weight recalculation.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import init_db
from tools.routing import (
    _data_confidence,
    classify_query,
    recalculate_weights,
    route_model,
    route_skill,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    c = init_db(tmp_path / "test.db")
    yield c
    c.close()


@pytest.fixture
def cold_conn(conn: sqlite3.Connection) -> sqlite3.Connection:
    """DB with < 10 outcomes (cold start)."""
    for i in range(5):
        conn.execute(
            "INSERT INTO task_outcomes (task_id, type, domain, complexity, outcome, model, skills_used) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (f"TASK-{i}", "feat", "BACKEND", "CLEAR", "success", "sonnet", "python-django"),
        )
    conn.commit()
    return conn


@pytest.fixture
def warm_conn(conn: sqlite3.Connection) -> sqlite3.Connection:
    """DB with 30+ outcomes (warm start)."""
    outcomes = [
        # BACKEND COMPLICATED — opus does better
        *[("feat", "BACKEND", "COMPLICATED", "success", "opus", "python-django") for _ in range(9)],
        *[("feat", "BACKEND", "COMPLICATED", "rework", "opus", "python-django") for _ in range(1)],
        *[("feat", "BACKEND", "COMPLICATED", "success", "sonnet", "python-django") for _ in range(4)],
        *[("feat", "BACKEND", "COMPLICATED", "rework", "sonnet", "python-django") for _ in range(3)],
        # FRONTEND CLEAR — sonnet does fine
        *[("feat", "FRONTEND", "CLEAR", "success", "sonnet", "nextjs-react") for _ in range(8)],
        *[("feat", "FRONTEND", "CLEAR", "rework", "sonnet", "nextjs-react") for _ in range(2)],
        # INFRA
        *[("chore", "INFRA", "CLEAR", "success", "haiku", "bash-linux") for _ in range(5)],
    ]
    for i, (typ, domain, comp, outcome, model, skills) in enumerate(outcomes):
        conn.execute(
            "INSERT INTO task_outcomes (task_id, type, domain, complexity, outcome, model, skills_used) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (f"TASK-{100 + i}", typ, domain, comp, outcome, model, skills),
        )
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# _data_confidence
# ---------------------------------------------------------------------------

class TestDataConfidence:
    def test_cold_start(self) -> None:
        assert _data_confidence(0) == 0.0
        assert _data_confidence(5) == 0.0
        assert _data_confidence(9) == 0.0

    def test_warming_up(self) -> None:
        conf = _data_confidence(15)
        assert 0.1 <= conf <= 0.4

    def test_moderate(self) -> None:
        conf = _data_confidence(35)
        assert 0.4 <= conf <= 0.7

    def test_high(self) -> None:
        conf = _data_confidence(60)
        assert 0.7 <= conf <= 0.9

    def test_capped(self) -> None:
        assert _data_confidence(1000) <= 0.9


# ---------------------------------------------------------------------------
# classify_query (J.1)
# ---------------------------------------------------------------------------

class TestClassifyQuery:
    def test_task_ref(self) -> None:
        result = classify_query("please check TASK-016 status")
        assert result["shape"] == "task_ref"
        assert result["confidence"] >= 0.95

    def test_behavioral(self) -> None:
        result = classify_query("how should i move a task to ready?")
        assert result["shape"] == "behavioral"
        assert result["confidence"] >= 0.9

    def test_identifier_by_call(self) -> None:
        result = classify_query("where is parse_task(task_md) used?")
        assert result["shape"] == "identifier"

    def test_identifier_by_path(self) -> None:
        result = classify_query("core/board_os/workflow.py transition rules")
        assert result["shape"] == "identifier"

    def test_past_pattern_en(self) -> None:
        result = classify_query("have we done this before in phase j?")
        assert result["shape"] == "past_pattern"

    def test_past_pattern_fa(self) -> None:
        result = classify_query("قبلا این مشکل رو داشتیم؟")
        assert result["shape"] == "past_pattern"

    def test_mixed_when_similar_confidence(self) -> None:
        result = classify_query("how do i debug parse_task in core/workflow.py")
        assert result["shape"] == "mixed"

    def test_conceptual_long_query(self) -> None:
        result = classify_query("explain the retrieval strategy across memory docs and tasks layers")
        assert result["shape"] == "conceptual"
        assert result["confidence"] >= 0.6

# ---------------------------------------------------------------------------
# cos_route_model
# ---------------------------------------------------------------------------

class TestRouteModel:
    def test_empty_db(self, conn: sqlite3.Connection) -> None:
        result = route_model(conn, complexity="COMPLICATED")
        assert result["recommended_model"] == "sonnet"
        assert result["confidence"] == 0.0
        assert "Cold start" in result["reason"]

    def test_cold_start(self, cold_conn: sqlite3.Connection) -> None:
        result = route_model(cold_conn, complexity="CLEAR")
        assert result["confidence"] == 0.0
        assert result["fallback_model"] == "sonnet"

    def test_warm_recommends_best(self, warm_conn: sqlite3.Connection) -> None:
        result = route_model(warm_conn, complexity="COMPLICATED", domain="BACKEND")
        assert result["recommended_model"] == "opus"
        assert result["confidence"] > 0

    def test_warm_includes_stats(self, warm_conn: sqlite3.Connection) -> None:
        result = route_model(warm_conn, complexity="COMPLICATED", domain="BACKEND")
        assert "model_stats" in result
        assert len(result["model_stats"]) > 0

    def test_insufficient_bucket_data(self, warm_conn: sqlite3.Connection) -> None:
        result = route_model(warm_conn, complexity="COMPLEX", domain="BACKEND")
        # No COMPLEX tasks exist — should fallback
        assert result["recommended_model"] == "opus"  # default for COMPLEX
        assert "Insufficient" in result["reason"]

    def test_all_complexities_have_defaults(self) -> None:
        from tools.routing import DEFAULT_MODELS
        for comp in ["CLEAR", "COMPLICATED", "COMPLEX", "CHAOTIC"]:
            assert comp in DEFAULT_MODELS

    def test_fallback_always_present(self, warm_conn: sqlite3.Connection) -> None:
        result = route_model(warm_conn, complexity="COMPLICATED", domain="BACKEND")
        assert "fallback_model" in result

    def test_data_points_returned(self, warm_conn: sqlite3.Connection) -> None:
        result = route_model(warm_conn, complexity="COMPLICATED")
        assert "data_points" in result
        assert result["data_points"] > 0


# ---------------------------------------------------------------------------
# cos_route_skill
# ---------------------------------------------------------------------------

class TestRouteSkill:
    def test_empty_db(self, conn: sqlite3.Connection) -> None:
        result = route_skill(conn, domain="BACKEND")
        assert result["fallback_source"] == "skill-enforcement.md"
        assert len(result["skills"]) > 0
        assert result["skills"][0]["name"] == "python-django"

    def test_cold_start_returns_static(self, cold_conn: sqlite3.Connection) -> None:
        result = route_skill(cold_conn, domain="BACKEND")
        assert result["fallback_source"] == "skill-enforcement.md"
        for s in result["skills"]:
            assert s["confidence"] == 0.0

    def test_warm_returns_data_driven(self, warm_conn: sqlite3.Connection) -> None:
        result = route_skill(warm_conn, domain="BACKEND")
        assert result["fallback_source"] == "data_driven"
        data_skills = [s for s in result["skills"] if s["reason"].startswith("data_driven")]
        assert len(data_skills) > 0

    def test_warm_includes_static_if_missing(self, warm_conn: sqlite3.Connection) -> None:
        result = route_skill(warm_conn, domain="DOCS")
        # DOCS has no historical data but might have static defaults
        assert "fallback_source" in result

    def test_frontend_domain(self, warm_conn: sqlite3.Connection) -> None:
        result = route_skill(warm_conn, domain="FRONTEND")
        skill_names = {s["name"] for s in result["skills"]}
        assert "nextjs-react" in skill_names

    def test_with_task_type_filter(self, warm_conn: sqlite3.Connection) -> None:
        result = route_skill(warm_conn, domain="BACKEND", task_type="feat")
        assert result["data_points"] > 0

    def test_unknown_domain(self, warm_conn: sqlite3.Connection) -> None:
        result = route_skill(warm_conn, domain="UNKNOWN")
        # Should still return without error
        assert "skills" in result


# ---------------------------------------------------------------------------
# Router weight tuning (TASK-148)
# ---------------------------------------------------------------------------

class TestRecalculateWeights:
    def test_empty_db(self, conn: sqlite3.Connection) -> None:
        result = recalculate_weights(conn)
        assert result["status"] == "ok"
        assert result["weights_updated"] == 0

    def test_recalculates_from_outcomes(self, warm_conn: sqlite3.Connection) -> None:
        result = recalculate_weights(warm_conn)
        assert result["status"] == "ok"
        assert result["weights_updated"] > 0

    def test_weights_stored_in_table(self, warm_conn: sqlite3.Connection) -> None:
        recalculate_weights(warm_conn)
        count = warm_conn.execute("SELECT COUNT(*) FROM routing_weights").fetchone()[0]
        assert count > 0

    def test_success_rate_correct(self, warm_conn: sqlite3.Connection) -> None:
        recalculate_weights(warm_conn)
        row = warm_conn.execute(
            "SELECT success_rate, sample_count FROM routing_weights "
            "WHERE domain = 'BACKEND' AND complexity = 'COMPLICATED' AND model = 'opus' "
            "LIMIT 1"
        ).fetchone()
        if row:
            assert 0.0 <= row[0] <= 1.0
            assert row[1] >= 5

    def test_idempotent(self, warm_conn: sqlite3.Connection) -> None:
        r1 = recalculate_weights(warm_conn)
        r2 = recalculate_weights(warm_conn)
        assert r1["weights_updated"] == r2["weights_updated"]
