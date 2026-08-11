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
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import init_db
from tools.learning import learn_extract
from tools.routing import failure_pattern_query, routing_drift
from tools.trajectory import (
    trajectory_digest_line,
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


class TestS1FreshProject:
    """Empty DB. Agent has no history, no trajectory, no patterns."""

    def test_trajectory_empty(self, fresh_db: sqlite3.Connection) -> None:
        result = trajectory_read(fresh_db)
        assert result["count"] == 0
        assert result["snapshots"] == []

    def test_drift_no_false_alarm(self, fresh_db: sqlite3.Connection) -> None:
        result = routing_drift(fresh_db)
        assert result["drift_detected"] is False
        assert result["new_outcomes_since_recalc"] == 0

    def test_failure_query_empty(self, fresh_db: sqlite3.Connection) -> None:
        result = failure_pattern_query(fresh_db)
        assert result["total_backtrack"] == 0
        assert result["patterns"] == []

    def test_digest_line_empty(self, fresh_db: sqlite3.Connection) -> None:
        line = trajectory_digest_line(fresh_db)
        assert line == ""

    def test_learn_extract_insufficient_data(self, fresh_db: sqlite3.Connection) -> None:
        result = learn_extract(fresh_db)
        assert result["status"] == "insufficient_data"


class TestS2ResearcherPersona:
    """Researcher completes investigation, logs trajectory with architectural decision."""

    def test_researcher_logs_trajectory(self, fresh_db: sqlite3.Connection) -> None:
        result = trajectory_snapshot(
            fresh_db,
            session_id="ses-claude-20260505-001",
            phase="Phase N.6 — SDK dispatch hardening",
            current_focus="Claude adapter deepening: formula dispatch cost tracking",
            architectural_decisions=[
                {
                    "decision": "EvidenceBundle is typed (not raw dict)",
                    "rationale": "Enables schema enforcement across formula outputs",
                }
            ],
            open_questions=[
                {"question": "Should uid scheme be in tool description?", "priority": "high"},
                {"question": "Cost budget cap enforcement strategy?", "priority": "medium"},
            ],
            next_logical_step="Implement cos_dispatch_formula_run cost capping",
            confidence=0.82,
        )
        assert result["status"] == "ok"

    def test_researcher_trajectory_readable_next_session(
        self, fresh_db: sqlite3.Connection
    ) -> None:
        trajectory_snapshot(
            fresh_db,
            session_id="ses-claude-20260505-001",
            phase="Phase N.6",
            current_focus="adapter deepening",
            next_logical_step="cost capping",
        )
        # Simulate next session reading
        read = trajectory_read(fresh_db, limit=1)
        snap = read["snapshots"][0]
        assert snap["phase"] == "Phase N.6"
        assert snap["next_logical_step"] == "cost capping"

    def test_digest_shows_trajectory_to_agent(self, fresh_db: sqlite3.Connection) -> None:
        import digest

        trajectory_snapshot(
            fresh_db,
            session_id="ses-claude-001",
            phase="Phase N.6",
            current_focus="adapter deepening",
            next_logical_step="cost capping",
        )
        body = digest.render(fresh_db)
        assert "## Trajectory" in body
        assert "Phase N.6" in body
        assert "adapter deepening" in body


class TestS3ImplementerBacktrack:
    """Implementer tries to build formula dispatch, scope too large, backtracks."""

    def test_implementer_logs_structured_backtrack(self, fresh_db: sqlite3.Connection) -> None:
        _add_backtrack(
            fresh_db,
            session_id="ses-claude-20260505-002",
            from_formula="implementer",
            to_formula="analyst",
            reason="Task scope exceeds single session; formula dispatch + cost tracking is two separate concerns",
            root_cause="scope_too_large",
            hypothesis="formula dispatch and cost tracking could be implemented together in one pass",
            failure_signal="diff grew to 400+ lines across 5 files before any test passed",
            corrective_action="split into TASK-A (dispatch) and TASK-B (cost tracking)",
        )

        row = fresh_db.execute(
            "SELECT root_cause, hypothesis, failure_signal, corrective_action "
            "FROM backtrack_events WHERE session_id='ses-claude-20260505-002'"
        ).fetchone()
        assert row["root_cause"] == "scope_too_large"
        assert "400+" in row["failure_signal"]

    def test_structured_backtrack_queryable(self, fresh_db: sqlite3.Connection) -> None:
        for i in range(3):
            _add_backtrack(
                fresh_db,
                session_id=f"ses-claude-{i}",
                from_formula="implementer",
                to_formula="analyst",
                reason="scope",
                root_cause="scope_too_large",
            )

        result = failure_pattern_query(fresh_db, root_cause="scope_too_large")
        assert result["patterns"][0]["count"] == 3
        assert result["patterns"][0]["root_cause"] == "scope_too_large"

    def test_invalid_root_cause_handled(self, fresh_db: sqlite3.Connection) -> None:
        # Simulate agent passing bad root_cause — query should still work
        fresh_db.execute(
            "INSERT INTO backtrack_events (session_id, from_formula, to_formula, reason, ts) "
            "VALUES ('s1', 'a', 'b', 'bad_cause', datetime('now'))"
        )
        fresh_db.commit()
        result = failure_pattern_query(fresh_db)
        # Row without root_cause (NULL) not counted in structured
        assert result["total_backtrack"] == 1
        assert result["total_structured"] == 0


class TestS4DebuggerMultiBacktrack:
    """Debugger gets stuck, backtracks 5 times, anti-paralysis fires."""

    def test_failure_anatomy_accumulates(self, fresh_db: sqlite3.Connection) -> None:
        causes = [
            "wrong_model",
            "missing_context",
            "wrong_model",
            "tool_failure",
            "wrong_model",
        ]
        for i, rc in enumerate(causes):
            _add_backtrack(
                fresh_db,
                session_id="ses-claude-debug",
                from_formula="debugger",
                to_formula="researcher",
                reason=f"attempt {i} failed",
                root_cause=rc,
            )

        result = failure_pattern_query(fresh_db)
        rc_counts = {p["root_cause"]: p["count"] for p in result["patterns"]}
        assert rc_counts["wrong_model"] == 3
        assert rc_counts["missing_context"] == 1
        assert rc_counts["tool_failure"] == 1

    def test_failure_patterns_extracted_by_learn_extract(
        self, fresh_db: sqlite3.Connection
    ) -> None:
        # Seed enough task outcomes for learn_extract threshold
        for i in range(10):
            _add_outcome(fresh_db, f"TASK-debug-{i}", outcome="rework")

        # Add backtrack pattern with 3+ same root_cause
        for i in range(3):
            _add_backtrack(
                fresh_db,
                session_id=f"s{i}",
                from_formula="debugger",
                to_formula="analyst",
                reason="wrong model",
                root_cause="wrong_model",
            )

        result = learn_extract(fresh_db, min_occurrences=3)
        assert result["status"] == "ok"

        # Check that a failure-type pattern was created
        failure_patterns = fresh_db.execute(
            "SELECT pattern, memory_type FROM learned_patterns WHERE memory_type='failure'"
        ).fetchall()
        assert len(failure_patterns) >= 1
        assert "wrong_model" in failure_patterns[0]["pattern"]
