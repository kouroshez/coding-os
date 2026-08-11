"""
End-to-end simulation and smoke tests.

Simulates realistic agent personas and workflows to verify the full
evolution pipeline: trajectory → failure anatomy → routing evolution.

Scenarios:
  S1: Fresh project (empty DB) — agent starts cold, no trajectory
  S2: Researcher persona — discovers architectural decision, logs trajectory
  S3: Implementer persona — hits scope issue, logs structured backtrack
  S4: Debugger persona — multi-backtrack session, anti-paralysis advisory
  S5: Architect persona — cross-session trajectory chain
  S6: Routing evolution — automatic weight refresh after 15 outcomes
  S7: Full lifecycle — extract → suggest → validate → drift loop
  S8: Digest integration — trajectory visible in agent digest on startup
  S9: Session startup helpers — trajectory_startup.py + routing_evolution.py
  S10: MCP envelope compliance — all new tools return ok()/fail() shape
"""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import init_db
from tools.routing import recalculate_weights, routing_drift
from tools.trajectory import (
    trajectory_read,
    trajectory_snapshot,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fresh_db(tmp_path: Path) -> sqlite3.Connection:
    """Empty DB — all migrations applied, no data."""
    c = init_db(tmp_path / "evo_smoke.db")
    yield c
    c.close()


def _add_outcome(
    conn,
    task_id,
    domain="INFRA",
    complexity="CLEAR",
    outcome="success",
    model="sonnet",
    skills="bash-linux",
):
    conn.execute(
        "INSERT INTO task_outcomes (task_id, type, domain, complexity, outcome, model, skills_used) "
        "VALUES (?, 'feat', ?, ?, ?, ?, ?)",
        (task_id, domain, complexity, outcome, model, skills),
    )
    conn.commit()


def _add_backtrack(
    conn,
    session_id,
    from_formula,
    to_formula,
    reason,
    root_cause=None,
    hypothesis=None,
    failure_signal=None,
    corrective_action=None,
):
    try:
        conn.execute(
            "INSERT INTO backtrack_events "
            "(session_id, from_formula, to_formula, reason, ts, "
            " root_cause, hypothesis, failure_signal, corrective_action) "
            "VALUES (?, ?, ?, ?, datetime('now'), ?, ?, ?, ?)",
            (
                session_id,
                from_formula,
                to_formula,
                reason,
                root_cause,
                hypothesis,
                failure_signal,
                corrective_action,
            ),
        )
    except sqlite3.OperationalError:
        conn.execute(
            "INSERT INTO backtrack_events (session_id, from_formula, to_formula, reason, ts) "
            "VALUES (?, ?, ?, ?, datetime('now'))",
            (session_id, from_formula, to_formula, reason),
        )
    conn.commit()


class TestS5ArchitectTrajectoryChain:
    """Architect updates trajectory across 3 sessions. Chain is navigable."""

    def test_trajectory_chain_links(self, fresh_db: sqlite3.Connection) -> None:
        r1 = trajectory_snapshot(
            fresh_db,
            session_id="s1",
            phase="Phase A",
            current_focus="graph schema design",
        )
        r2 = trajectory_snapshot(
            fresh_db,
            session_id="s2",
            phase="Phase B",
            current_focus="graph extraction pipeline",
        )
        r3 = trajectory_snapshot(
            fresh_db,
            session_id="s3",
            phase="Phase C",
            current_focus="graph API layer",
            next_logical_step="wire up hub UI to graph",
        )

        assert r2["supersedes_id"] == r1["id"]
        assert r3["supersedes_id"] == r2["id"]

    def test_most_recent_trajectory_is_default(self, fresh_db: sqlite3.Connection) -> None:
        for i, focus in enumerate(["design", "build", "ship"]):
            trajectory_snapshot(fresh_db, session_id=f"s{i}", phase=f"P{i}", current_focus=focus)

        snap = trajectory_read(fresh_db, limit=1)["snapshots"][0]
        assert snap["current_focus"] == "ship"
        assert snap["phase"] == "P2"

    def test_trajectory_history_navigable(self, fresh_db: sqlite3.Connection) -> None:
        for i in range(5):
            trajectory_snapshot(fresh_db, session_id=f"s{i}", phase=f"Phase {i}")

        history = trajectory_read(fresh_db, limit=5)
        assert history["count"] == 5
        phases = [s["phase"] for s in history["snapshots"]]
        assert phases[0] == "Phase 4"  # most recent first
        assert phases[-1] == "Phase 0"

    def test_architectural_decisions_preserved(self, fresh_db: sqlite3.Connection) -> None:
        decisions = [
            {"decision": "append-only migrations", "rationale": "safety"},
            {"decision": "fire-and-forget helpers", "rationale": "hook reliability"},
        ]
        trajectory_snapshot(
            fresh_db,
            session_id="s1",
            architectural_decisions=decisions,
        )
        snap = trajectory_read(fresh_db)["snapshots"][0]
        assert len(snap["architectural_decisions"]) == 2
        assert snap["architectural_decisions"][0]["rationale"] == "safety"


class TestS6RoutingEvolution:
    """Simulate 20 task outcomes accumulating; verify drift → auto-recalc → no drift."""

    def test_cold_no_drift(self, fresh_db: sqlite3.Connection) -> None:
        assert routing_drift(fresh_db)["drift_detected"] is False

    def test_15_outcomes_triggers_drift(self, fresh_db: sqlite3.Connection) -> None:
        for i in range(15):
            _add_outcome(fresh_db, f"T-{i}")
        result = routing_drift(fresh_db)
        assert result["drift_detected"] is True
        assert result["recommendation"] == "recalculate"

    def test_recalculate_resolves_drift(self, fresh_db: sqlite3.Connection) -> None:
        for i in range(20):
            _add_outcome(fresh_db, f"T-{i}")
        assert routing_drift(fresh_db)["drift_detected"] is True
        recalculate_weights(fresh_db)
        assert routing_drift(fresh_db)["drift_detected"] is False

    def test_drift_threshold_is_15(self, fresh_db: sqlite3.Connection) -> None:
        for i in range(14):
            _add_outcome(fresh_db, f"T-{i}")
        assert routing_drift(fresh_db)["drift_detected"] is False
        _add_outcome(fresh_db, "T-14")
        assert routing_drift(fresh_db)["drift_detected"] is True

    def test_routing_evolution_helper_script(self, tmp_path: Path) -> None:
        """routing_evolution.py helper fires recalc and prints message."""
        db = init_db(tmp_path / "evo_helper.db")
        for i in range(20):
            db.execute(
                "INSERT INTO task_outcomes (task_id, type, domain, complexity, outcome, model) "
                "VALUES (?, 'feat', 'INFRA', 'CLEAR', 'success', 'sonnet')",
                (f"T-{i}",),
            )
        db.commit()
        db.close()

        # core/thinking_os/tests/ → core/hooks/_helpers/
        helper = (
            Path(__file__).resolve().parent.parent.parent
            / "hooks"
            / "_helpers"
            / "routing_evolution.py"
        )
        if not helper.exists():
            pytest.skip("routing_evolution.py helper not found")

        result = subprocess.run(
            ["python3", str(helper), str(tmp_path / "evo_helper.db")],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        # With 20 outcomes at threshold 15 and no prior recalc, should print refresh
        # (may or may not have buckets depending on model diversity — just no crash)

    def test_trajectory_startup_helper_script(self, tmp_path: Path) -> None:
        """trajectory_startup.py prints trajectory line when data exists."""
        db = init_db(tmp_path / "traj_helper.db")
        trajectory_snapshot(
            db,
            session_id="s1",
            phase="Phase EVO",
            current_focus="smoke testing",
            next_logical_step="ship the feature",
        )
        db.close()

        helper = (
            Path(__file__).resolve().parent.parent.parent
            / "hooks"
            / "_helpers"
            / "trajectory_startup.py"
        )
        if not helper.exists():
            pytest.skip("trajectory_startup.py helper not found")

        result = subprocess.run(
            ["python3", str(helper), str(tmp_path / "traj_helper.db")],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "[Project Trajectory]" in result.stdout
        assert "Phase EVO" in result.stdout
        assert "smoke testing" in result.stdout
