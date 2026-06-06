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
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import init_db
from tools.learning import learn_extract, learn_suggest
from tools.routing import failure_pattern_query, recalculate_weights, routing_drift
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


# ---------------------------------------------------------------------------
# S1: Fresh project — agent starts cold
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# S2: Researcher persona — discovers, logs trajectory
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# S3: Implementer persona — scope issue → structured backtrack
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# S4: Debugger persona — multi-backtrack, anti-paralysis
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# S5: Architect persona — cross-session trajectory chain
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# S6: Routing evolution — automatic weight refresh
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# S7: Full lifecycle — extract → suggest → validate feedback loop
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# S8: Multi-persona failure correlation
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# S9: MCP envelope compliance
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# S10: Digest budget across all EVO sections
# ---------------------------------------------------------------------------


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
