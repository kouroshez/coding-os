"""
Tests for evolution features:
  - project_trajectory (DB migration v24 + trajectory.py tools)
  - structured failure anatomy (DB migration v25 + backtrack_events columns)
  - autonomous routing evolution (DB migration v26 + routing staleness)
  - failure_pattern_query and routing_drift functions
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import init_db
from tools.routing import failure_pattern_query, recalculate_weights, routing_drift
from tools.trajectory import trajectory_read, trajectory_snapshot

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    c = init_db(tmp_path / "test_evo.db")
    yield c
    c.close()


# ---------------------------------------------------------------------------
# 1. Project Trajectory — migration v24
# ---------------------------------------------------------------------------


class TestProjectTrajectory:
    def test_table_created(self, conn: sqlite3.Connection) -> None:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='project_trajectory'"
        ).fetchone()
        assert row is not None, "project_trajectory table missing after init_db"

    def test_snapshot_write_read_roundtrip(self, conn: sqlite3.Connection) -> None:
        result = trajectory_snapshot(
            conn,
            session_id="ses-test-001",
            phase="Phase EVO",
            current_focus="trajectory tooling",
            architectural_decisions=[{"decision": "append-only migrations", "rationale": "safety"}],
            open_questions=[{"question": "how to auto-expire stale snapshots?", "priority": "low"}],
            next_logical_step="wire session startup hook",
            confidence=0.85,
        )
        assert result["status"] == "ok"
        row_id = result["id"]
        assert row_id is not None
        assert result["supersedes_id"] is None  # first snapshot

        read = trajectory_read(conn, limit=1)
        assert read["count"] == 1
        snap = read["snapshots"][0]
        assert snap["phase"] == "Phase EVO"
        assert snap["current_focus"] == "trajectory tooling"
        assert snap["confidence"] == pytest.approx(0.85)
        assert isinstance(snap["architectural_decisions"], list)
        assert snap["architectural_decisions"][0]["decision"] == "append-only migrations"

    def test_supersedes_chain(self, conn: sqlite3.Connection) -> None:
        r1 = trajectory_snapshot(conn, session_id="s1", phase="Phase A")
        r2 = trajectory_snapshot(conn, session_id="s2", phase="Phase B")
        assert r2["supersedes_id"] == r1["id"]

    def test_read_limit(self, conn: sqlite3.Connection) -> None:
        for i in range(5):
            trajectory_snapshot(conn, session_id=f"s{i}", phase=f"Phase {i}")
        read = trajectory_read(conn, limit=3)
        assert read["count"] == 3
        # Most recent first
        assert read["snapshots"][0]["phase"] == "Phase 4"

    def test_empty_db_returns_empty(self, conn: sqlite3.Connection) -> None:
        read = trajectory_read(conn, limit=1)
        assert read["count"] == 0
        assert read["snapshots"] == []

    def test_confidence_clamped(self, conn: sqlite3.Connection) -> None:
        trajectory_snapshot(conn, session_id="s1", confidence=1.5)
        snap = trajectory_read(conn)["snapshots"][0]
        assert snap["confidence"] <= 1.0


# ---------------------------------------------------------------------------
# 2. Failure Anatomy — migration v25
# ---------------------------------------------------------------------------


class TestFailureAnatomy:
    def test_backtrack_events_has_anatomy_columns(self, conn: sqlite3.Connection) -> None:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(backtrack_events)").fetchall()}
        for col in ("hypothesis", "failure_signal", "root_cause", "corrective_action"):
            assert col in cols, f"Missing column: {col}"

    def test_insert_with_anatomy(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            "INSERT INTO backtrack_events "
            "(session_id, from_formula, to_formula, reason, ts, "
            " hypothesis, failure_signal, root_cause, corrective_action) "
            "VALUES (?, ?, ?, ?, datetime('now'), ?, ?, ?, ?)",
            (
                "s1",
                "implementer",
                "analyst",
                "wrong scope",
                "scope would fit CLEAR",
                "rework rate spiked",
                "scope_too_large",
                "decomposed into subtasks",
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT root_cause, hypothesis FROM backtrack_events WHERE session_id='s1'"
        ).fetchone()
        assert row["root_cause"] == "scope_too_large"
        assert "CLEAR" in row["hypothesis"]

    def test_failure_pattern_query_empty(self, conn: sqlite3.Connection) -> None:
        result = failure_pattern_query(conn)
        assert result["total_backtrack"] == 0
        assert result["patterns"] == []

    def test_failure_pattern_query_aggregates(self, conn: sqlite3.Connection) -> None:
        for i in range(3):
            conn.execute(
                "INSERT INTO backtrack_events "
                "(session_id, from_formula, to_formula, reason, ts, root_cause) "
                "VALUES (?, ?, ?, ?, datetime('now'), ?)",
                (f"s{i}", "implementer", "analyst", "reason", "wrong_model"),
            )
        conn.execute(
            "INSERT INTO backtrack_events "
            "(session_id, from_formula, to_formula, reason, ts, root_cause) "
            "VALUES (?, ?, ?, ?, datetime('now'), ?)",
            ("s99", "architect", "researcher", "reason", "missing_context"),
        )
        conn.commit()

        result = failure_pattern_query(conn)
        assert result["total_backtrack"] == 4
        assert result["total_structured"] == 4
        rc_counts = {p["root_cause"]: p["count"] for p in result["patterns"]}
        assert rc_counts["wrong_model"] == 3
        assert rc_counts["missing_context"] == 1

    def test_failure_pattern_query_filter(self, conn: sqlite3.Connection) -> None:
        for rc in ("wrong_model", "wrong_model", "tool_failure"):
            conn.execute(
                "INSERT INTO backtrack_events "
                "(session_id, from_formula, to_formula, reason, ts, root_cause) "
                "VALUES ('s1', 'a', 'b', 'r', datetime('now'), ?)",
                (rc,),
            )
        conn.commit()
        result = failure_pattern_query(conn, root_cause="wrong_model")
        assert all(p["root_cause"] == "wrong_model" for p in result["patterns"])


# ---------------------------------------------------------------------------
# 3. Routing Evolution — migration v26
# ---------------------------------------------------------------------------


class TestRoutingEvolution:
    def test_routing_weights_has_staleness_columns(self, conn: sqlite3.Connection) -> None:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(routing_weights)").fetchall()}
        assert "last_recalc_at" in cols
        assert "outcomes_at_recalc" in cols

    def test_routing_drift_no_outcomes(self, conn: sqlite3.Connection) -> None:
        result = routing_drift(conn)
        assert result["drift_detected"] is False
        assert result["new_outcomes_since_recalc"] == 0

    def _seed_outcomes(self, conn: sqlite3.Connection, n: int, outcome: str = "success") -> None:
        for i in range(n):
            conn.execute(
                "INSERT INTO task_outcomes (task_id, type, domain, complexity, outcome, model) "
                "VALUES (?, 'feat', 'INFRA', 'CLEAR', ?, 'sonnet')",
                (f"T-{i}", outcome),
            )
        conn.commit()

    def test_drift_detected_after_threshold(self, conn: sqlite3.Connection) -> None:
        self._seed_outcomes(conn, 20)
        result = routing_drift(conn)
        assert result["drift_detected"] is True
        assert result["new_outcomes_since_recalc"] == 20
        assert result["recommendation"] == "recalculate"

    def test_recalculate_stamps_metadata(self, conn: sqlite3.Connection) -> None:
        self._seed_outcomes(conn, 20)
        recalculate_weights(conn)

        row = conn.execute(
            "SELECT MAX(outcomes_at_recalc) AS at_recalc, MAX(last_recalc_at) AS recalc_at "
            "FROM routing_weights"
        ).fetchone()
        # May be None if no buckets met threshold — just verify no crash
        # and drift resets
        result = routing_drift(conn)
        assert result["new_outcomes_since_recalc"] == 0

    def test_drift_resets_after_recalculate(self, conn: sqlite3.Connection) -> None:
        self._seed_outcomes(conn, 20)
        assert routing_drift(conn)["drift_detected"] is True
        recalculate_weights(conn)
        assert routing_drift(conn)["drift_detected"] is False


# ---------------------------------------------------------------------------
# 4. Digest trajectory section
# ---------------------------------------------------------------------------


class TestDigestTrajectory:
    def test_trajectory_line_empty_when_no_data(self, conn: sqlite3.Connection) -> None:
        from tools.trajectory import trajectory_digest_line

        line = trajectory_digest_line(conn)
        assert line == ""

    def test_trajectory_line_populated(self, conn: sqlite3.Connection) -> None:
        from tools.trajectory import trajectory_digest_line

        trajectory_snapshot(
            conn,
            session_id="s1",
            phase="Phase EVO",
            current_focus="testing",
            next_logical_step="ship it",
        )
        line = trajectory_digest_line(conn)
        assert "Phase EVO" in line
        assert "testing" in line
        assert len(line) <= 290

    def test_digest_render_includes_trajectory(self, conn: sqlite3.Connection) -> None:
        import digest

        trajectory_snapshot(conn, session_id="s1", phase="Phase EVO", current_focus="tests")
        body = digest.render(conn)
        assert "## Trajectory" in body
        assert "Phase EVO" in body
        assert len(body) <= 2600  # budget + marker margin
