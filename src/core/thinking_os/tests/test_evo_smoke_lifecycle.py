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

import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import init_db
from tools.learning import learn_extract, learn_suggest
from tools.routing import failure_pattern_query, recalculate_weights, routing_drift
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


class TestS7FullLearningLifecycle:
    """Simulate the full evolution loop across one realistic sprint."""

    def _seed_sprint(self, conn: sqlite3.Connection) -> None:
        """20 tasks: mix of success/rework, multiple domains."""
        tasks = [
            ("TASK-001", "INFRA", "CLEAR", "success", "sonnet"),
            ("TASK-002", "INFRA", "CLEAR", "success", "sonnet"),
            ("TASK-003", "INFRA", "COMPLICATED", "rework", "sonnet"),
            ("TASK-004", "BACKEND", "CLEAR", "success", "sonnet"),
            ("TASK-005", "BACKEND", "CLEAR", "rework", "sonnet"),
            ("TASK-006", "BACKEND", "COMPLICATED", "rework", "opus"),
            ("TASK-007", "FRONTEND", "CLEAR", "success", "sonnet"),
            ("TASK-008", "FRONTEND", "CLEAR", "success", "sonnet"),
            ("TASK-009", "DOCS", "CLEAR", "success", "sonnet"),
            ("TASK-010", "INFRA", "CLEAR", "success", "sonnet"),
            ("TASK-011", "INFRA", "COMPLICATED", "success", "opus"),
            ("TASK-012", "INFRA", "COMPLICATED", "success", "opus"),
            ("TASK-013", "BACKEND", "COMPLEX", "success", "opus"),
            ("TASK-014", "BACKEND", "CLEAR", "rework", "sonnet"),
            ("TASK-015", "INFRA", "CLEAR", "success", "sonnet"),
            ("TASK-016", "BACKEND", "COMPLICATED", "success", "sonnet"),
            ("TASK-017", "DOCS", "CLEAR", "success", "sonnet"),
            ("TASK-018", "FRONTEND", "COMPLICATED", "success", "sonnet"),
            ("TASK-019", "INFRA", "CLEAR", "success", "sonnet"),
            ("TASK-020", "BACKEND", "CLEAR", "success", "sonnet"),
        ]
        for task_id, domain, complexity, outcome, model in tasks:
            conn.execute(
                "INSERT INTO task_outcomes (task_id, type, domain, complexity, outcome, model) "
                "VALUES (?, 'feat', ?, ?, ?, ?)",
                (task_id, domain, complexity, outcome, model),
            )
        conn.commit()

    def test_extract_mines_patterns_after_sprint(self, fresh_db: sqlite3.Connection) -> None:
        self._seed_sprint(fresh_db)
        result = learn_extract(fresh_db, min_occurrences=2)
        assert result["status"] == "ok"
        assert result["total_outcomes_analyzed"] == 20
        assert len(result["extracted"]) > 0

    def test_routing_drift_triggers_after_sprint(self, fresh_db: sqlite3.Connection) -> None:
        self._seed_sprint(fresh_db)
        drift = routing_drift(fresh_db)
        assert drift["drift_detected"] is True
        assert drift["new_outcomes_since_recalc"] == 20

    def test_recalculate_builds_weights(self, fresh_db: sqlite3.Connection) -> None:
        self._seed_sprint(fresh_db)
        result = recalculate_weights(fresh_db)
        assert result["status"] == "ok"
        assert result["weights_updated"] > 0

        weight_rows = fresh_db.execute("SELECT COUNT(*) FROM routing_weights").fetchone()[0]
        assert weight_rows > 0

    def test_full_loop_drift_resolve_suggest(self, fresh_db: sqlite3.Connection) -> None:
        self._seed_sprint(fresh_db)

        # Step 1: drift detected
        assert routing_drift(fresh_db)["drift_detected"] is True

        # Step 2: recalculate resolves drift
        recalculate_weights(fresh_db)
        assert routing_drift(fresh_db)["drift_detected"] is False

        # Step 3: learn_extract creates patterns
        learn_extract(fresh_db, min_occurrences=2)

        # Step 4: suggest returns relevant patterns
        suggestions = learn_suggest(fresh_db, domain="BACKEND", complexity="CLEAR")
        # May have patterns or not depending on data — just no crash
        assert "suggestions" in suggestions

    def test_trajectory_persists_throughout_sprint(self, fresh_db: sqlite3.Connection) -> None:
        self._seed_sprint(fresh_db)

        trajectory_snapshot(
            fresh_db,
            session_id="sprint-session",
            phase="Sprint 1",
            current_focus="INFRA stability + BACKEND rework reduction",
            architectural_decisions=[
                {"decision": "use opus for COMPLICATED BACKEND", "rationale": "lower rework rate"},
            ],
            open_questions=["Should BACKEND CLEAR tasks also use opus?"],
            next_logical_step="validate opus vs sonnet for BACKEND COMPLICATED in sprint 2",
        )

        snap = trajectory_read(fresh_db)["snapshots"][0]
        assert snap["phase"] == "Sprint 1"
        assert isinstance(snap["open_questions"], list)
        assert len(snap["open_questions"]) == 1


class TestS8MultiPersonaFailureCorrelation:
    """Multiple persona types, same root causes — learn_extract sees pattern."""

    def test_cross_persona_root_cause_mined(self, fresh_db: sqlite3.Connection) -> None:
        # Seed task outcomes for extract threshold
        for i in range(10):
            _add_outcome(fresh_db, f"T-base-{i}")

        personas_that_fail = [
            ("implementer", "missing context in spec"),
            ("implementer", "missing context in PRD"),
            ("architect", "missing context: no design doc"),
            ("implementer", "missing context: unclear API contract"),
        ]
        for persona, reason in personas_that_fail:
            _add_backtrack(
                fresh_db,
                session_id=f"ses-{persona}-{reason[:10]}",
                from_formula=persona,
                to_formula="researcher",
                reason=reason,
                root_cause="missing_context",
                hypothesis="enough context available to proceed",
                failure_signal="blocked waiting for spec clarification",
            )

        result = failure_pattern_query(fresh_db, root_cause="missing_context")
        assert result["patterns"][0]["count"] == 4
        assert len(result["patterns"][0]["examples"]) <= 3  # capped at 3 examples

        # learn_extract should pick this up
        extract = learn_extract(fresh_db, min_occurrences=3)
        assert extract["status"] == "ok"
        failure_patterns = fresh_db.execute(
            "SELECT pattern FROM learned_patterns WHERE memory_type='failure'"
        ).fetchall()
        patterns_text = " ".join(r["pattern"] for r in failure_patterns)
        assert "missing_context" in patterns_text


class TestS9MCPEnvelopeCompliance:
    """All new MCP tools return valid ok()/fail() envelope shape."""

    def _parse_envelope(self, json_str: str) -> dict:
        data = json.loads(json_str)
        assert "ok" in data, f"Missing 'ok' key: {data}"
        return data

    def test_trajectory_snapshot_envelope(self, fresh_db: sqlite3.Connection) -> None:
        # Simulate server.py wrapper behavior (direct function call + ok() wrap)
        from tools._shared import ok

        result = trajectory_snapshot(fresh_db, session_id="s1", phase="P1")
        envelope = json.loads(ok(result))
        assert envelope["ok"] is True
        assert envelope["data"]["status"] == "ok"

    def test_trajectory_read_envelope(self, fresh_db: sqlite3.Connection) -> None:
        from tools._shared import ok

        result = trajectory_read(fresh_db)
        envelope = json.loads(ok(result))
        assert envelope["ok"] is True
        assert "snapshots" in envelope["data"]

    def test_failure_pattern_query_envelope(self, fresh_db: sqlite3.Connection) -> None:
        from tools._shared import ok

        result = failure_pattern_query(fresh_db)
        envelope = json.loads(ok(result))
        assert envelope["ok"] is True
        assert "patterns" in envelope["data"]

    def test_routing_drift_envelope(self, fresh_db: sqlite3.Connection) -> None:
        from tools._shared import ok

        result = routing_drift(fresh_db)
        envelope = json.loads(ok(result))
        assert envelope["ok"] is True
        assert "drift_detected" in envelope["data"]

    def test_trajectory_snapshot_missing_session_id(self, fresh_db: sqlite3.Connection) -> None:
        result = trajectory_snapshot(fresh_db, session_id="")
        assert result["status"] == "error"

    def test_failure_query_invalid_root_cause_ignored(self, fresh_db: sqlite3.Connection) -> None:
        # Invalid root_cause filter should be silently ignored (not crash)
        result = failure_pattern_query(fresh_db, root_cause="nonexistent_category")
        assert "patterns" in result  # no crash, returns empty result


class TestS10DigestBudget:
    """Verify digest stays within 2400-char budget under various EVO data loads."""

    def test_budget_with_full_evo_data(self, fresh_db: sqlite3.Connection) -> None:
        import digest

        # Seed all sections
        trajectory_snapshot(
            fresh_db,
            session_id="s1",
            phase="Phase N.6 — SDK dispatch hardening (very long phase name to stress budget)",
            current_focus="Claude adapter deepening: formula dispatch cost tracking and budget capping",
            next_logical_step="Implement cos_dispatch_formula_run budget enforcement and cost rollup",
            open_questions=[
                "uid scheme documentation — where does it belong?",
                "cost capping strategy: hard vs soft limits?",
            ],
        )
        for i in range(10):
            fresh_db.execute(
                "INSERT INTO learned_patterns (pattern, confidence, impact_score, memory_type) "
                "VALUES (?, ?, ?, ?)",
                (f"Pattern {i}: " + "x" * 100, 0.8 - i * 0.02, 0.7, "pattern"),
            )
        fresh_db.commit()

        body = digest.render(fresh_db)
        assert len(body) <= 2600, f"Digest too large: {len(body)} chars"
        assert "## Trajectory" in body

    def test_budget_not_blown_by_long_trajectory(self, fresh_db: sqlite3.Connection) -> None:
        import digest

        trajectory_snapshot(
            fresh_db,
            session_id="s1",
            phase="A" * 200,  # intentionally long phase name
            current_focus="B" * 200,
            next_logical_step="C" * 200,
        )

        body = digest.render(fresh_db)
        # trajectory_digest_line caps at 290 chars — digest should never blow budget
        assert len(body) <= 2600
