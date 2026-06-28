"""
Tests for MCP routing tools (TASK-145, TASK-148).

Covers cold start fallback, warm recommendation, sample threshold,
static rules fallback, data-driven suggestions, empty DB,
and routing weight recalculation.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import init_db
from tools.routing import (
    _data_confidence,
    _sample_beta,
    recalculate_weights,
    route_model,
    route_model_bandit,
    route_skill,
    reviewer_model,
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
        *[
            ("feat", "BACKEND", "COMPLICATED", "success", "sonnet", "python-django")
            for _ in range(4)
        ],
        *[
            ("feat", "BACKEND", "COMPLICATED", "rework", "sonnet", "python-django")
            for _ in range(3)
        ],
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

    def test_credits_per_role_model_not_orchestrator(self, conn: sqlite3.Connection) -> None:
        """TASK-473 P4-9: a session under opus that dispatched the role to sonnet
        must credit sonnet (formula_dispatches.model), not opus (task_outcomes.model)."""
        for i in range(12):
            tid = f"TASK-{200 + i}"
            conn.execute(
                "INSERT INTO task_outcomes (task_id, type, domain, complexity, outcome, model) "
                "VALUES (?, 'feat', 'BACKEND', 'COMPLICATED', 'success', 'opus')",
                (tid,),
            )
            conn.execute(
                "INSERT INTO formula_dispatches "
                "(session_id, task_marker, persona_id, formula_id, input_hash, status, ts, model) "
                "VALUES (?, ?, 'implementer', 'f', 'h', 'ok', datetime('now'), 'sonnet')",
                (f"ses-{i}", tid),
            )
        conn.commit()
        result = route_model(conn, complexity="COMPLICATED", domain="BACKEND")
        assert result["recommended_model"] == "sonnet"
        models = {s["model"] for s in result.get("model_stats", [])}
        assert "sonnet" in models and "opus" not in models

    def test_orchestrator_model_used_when_no_dispatch(self, conn: sqlite3.Connection) -> None:
        """A task done directly (no formula_dispatch) still attributes to its
        orchestrator model — the COALESCE fallback, so direct work isn't lost."""
        for i in range(12):
            conn.execute(
                "INSERT INTO task_outcomes (task_id, type, domain, complexity, outcome, model) "
                "VALUES (?, 'feat', 'BACKEND', 'COMPLICATED', 'success', 'haiku')",
                (f"TASK-{300 + i}",),
            )
        conn.commit()
        result = route_model(conn, complexity="COMPLICATED", domain="BACKEND")
        assert result["recommended_model"] == "haiku"


class TestRouteModelBandit:
    def test_flag_off_delegates_to_route_model(self, warm_conn, monkeypatch) -> None:
        monkeypatch.delenv("COS_ROUTER_BANDIT", raising=False)
        result = route_model_bandit(warm_conn, complexity="COMPLICATED", domain="BACKEND")
        assert "method" not in result  # frequentist path, byte-identical
        assert result["recommended_model"] == "opus"

    def test_cold_start_delegates_even_when_flag_on(self, cold_conn, monkeypatch) -> None:
        monkeypatch.setenv("COS_ROUTER_BANDIT", "1")
        result = route_model_bandit(cold_conn, complexity="CLEAR")
        assert "method" not in result  # cold-start delegates to route_model
        assert result["confidence"] == 0.0

    def test_warm_samples_thompson(self, warm_conn, monkeypatch) -> None:
        monkeypatch.setenv("COS_ROUTER_BANDIT", "1")
        result = route_model_bandit(warm_conn, complexity="COMPLICATED", domain="BACKEND")
        assert result["method"] == "thompson"
        assert result["recommended_model"] in {"opus", "sonnet"}
        assert 0.0 <= result["confidence"] <= 1.0
        for s in result["model_stats"]:
            assert s["alpha"] >= 1 and s["beta"] >= 1  # Beta(1+success, 1+failure)

    def test_warm_prefers_higher_success_model(self, warm_conn, monkeypatch) -> None:
        import random

        monkeypatch.setenv("COS_ROUTER_BANDIT", "1")
        random.seed(42)
        picks = [
            route_model_bandit(warm_conn, complexity="COMPLICATED", domain="BACKEND")["recommended_model"]
            for _ in range(50)
        ]
        assert picks.count("opus") > picks.count("sonnet")  # opus 90% beats sonnet 57%

    def test_sample_beta_in_unit_interval(self) -> None:
        for a, b in [(1.0, 1.0), (10.0, 2.0), (2.0, 10.0), (1.5, 1.5)]:
            for _ in range(20):
                assert 0.0 <= _sample_beta(a, b) <= 1.0

    def test_confidence_is_selected_model_posterior_mean(self, warm_conn, monkeypatch) -> None:
        monkeypatch.setenv("COS_ROUTER_BANDIT", "1")
        r = route_model_bandit(warm_conn, complexity="COMPLICATED", domain="BACKEND")
        assert 0.0 <= r["confidence"] <= 1.0  # a posterior mean, not a raw sample
        sel = next(s for s in r["model_stats"] if s["model"] == r["recommended_model"])
        assert r["confidence"] == round(sel["alpha"] / (sel["alpha"] + sel["beta"]), 2)

    def test_large_cost_tilt_keeps_confidence_in_unit_interval(self, warm_conn, monkeypatch) -> None:
        monkeypatch.setenv("COS_ROUTER_BANDIT", "1")
        monkeypatch.setenv("COS_ROUTER_COST_TILT", "9")  # sinks every tilted score far below 0
        r = route_model_bandit(warm_conn, complexity="COMPLICATED", domain="BACKEND")
        assert 0.0 <= r["confidence"] <= 1.0  # -inf seed always selects a real model
        assert r["recommended_model"] in {"opus", "sonnet"}


class TestCostRouting:
    def test_reviewer_model_downgrades_one_tier(self) -> None:
        assert reviewer_model("opus") == "sonnet"
        assert reviewer_model("sonnet") == "haiku"
        assert reviewer_model("haiku") == "haiku"
        assert reviewer_model("claude-opus-4-8") == "sonnet"
        assert reviewer_model("") == ""


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
# Router weight tuning
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
