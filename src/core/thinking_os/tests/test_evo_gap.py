"""
Tests for evolution gap closure:
  Gap A — auto-trajectory snapshot at session end
  Gap B — tool failure capture → observations → session aggregation
  Gap C — mid-session adaptation (suggested_action in cos_backtrack_log)
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import init_db

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    c = init_db(tmp_path / "test_evo_gap.db")
    c.row_factory = sqlite3.Row
    yield c
    c.close()


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    p = tmp_path / "test_gap.db"
    c = init_db(p)
    c.close()
    return p


# ---------------------------------------------------------------------------
# Gap B1 — tool_failure_capture.py logic
# ---------------------------------------------------------------------------


class TestToolFailureCapture:
    """Unit tests for core/hooks/_helpers/tool_failure_capture.py."""

    def _import_capture(self):
        helpers = Path(__file__).resolve().parent.parent.parent / "hooks" / "_helpers"
        sys.path.insert(0, str(helpers))
        import tool_failure_capture

        return tool_failure_capture

    def test_capture_blocked_event_writes_hook_block(self, conn):
        mod = self._import_capture()
        payload = {
            "tool_name": "Edit",
            "error": "BLOCKED: Bare except: pass detected",
            "tool_input": {"file_path": "/some/file.py"},
        }
        status = mod.capture(conn, "sess-001", payload)
        assert status == "captured"
        row = conn.execute("SELECT * FROM observations WHERE session_id='sess-001'").fetchone()
        assert row is not None
        assert row["memory_type"] == "hook_block"
        assert row["observation_type"] == "tool_failure"
        assert abs(row["impact_score"] - 0.6) < 0.01

    def test_capture_non_bash_unblocked_error_writes_error(self, conn):
        mod = self._import_capture()
        payload = {
            "tool_name": "Read",
            "error": "File not found: /missing.py",
            "tool_input": {"file_path": "/missing.py"},
        }
        status = mod.capture(conn, "sess-002", payload)
        assert status == "captured"
        row = conn.execute("SELECT * FROM observations WHERE session_id='sess-002'").fetchone()
        assert row["memory_type"] == "error"
        assert abs(row["impact_score"] - 0.3) < 0.01

    def test_capture_bash_unblocked_skipped(self, conn):
        mod = self._import_capture()
        payload = {
            "tool_name": "Bash",
            "error": "exit code 1: some failure",
            "tool_input": {"command": "ls /nonexistent"},
        }
        status = mod.capture(conn, "sess-003", payload)
        assert status == "skipped_noisy"

    def test_capture_bash_blocked_still_captured(self, conn):
        mod = self._import_capture()
        payload = {
            "tool_name": "Bash",
            "error": "BLOCKED: dangerous rm -rf attempted",
            "tool_input": {"command": "rm -rf /"},
        }
        status = mod.capture(conn, "sess-004", payload)
        assert status == "captured"
        row = conn.execute("SELECT * FROM observations WHERE session_id='sess-004'").fetchone()
        assert row["memory_type"] == "hook_block"

    def test_capture_dedup_within_60s(self, conn):
        mod = self._import_capture()
        payload = {
            "tool_name": "Edit",
            "error": "BLOCKED: bad pattern",
            "tool_input": {},
        }
        s1 = mod.capture(conn, "sess-005", payload)
        s2 = mod.capture(conn, "sess-005", payload)
        assert s1 == "captured"
        assert s2 == "deduped"

    def test_capture_empty_payload_skipped(self, conn):
        mod = self._import_capture()
        status = mod.capture(conn, "sess-006", {})
        assert status == "empty_payload"

    def test_main_no_args_exits_zero(self):
        mod = self._import_capture()
        assert mod.main(["tool_failure_capture.py"]) == 0


# ---------------------------------------------------------------------------
# Gap B4 — session aggregation: ≥2 tool_failures → backtrack_event
# ---------------------------------------------------------------------------


class TestToolFailureAggregation:
    """Tests for _aggregate_tool_failures in trajectory_autosnap.py."""

    def _import_autosnap(self):
        helpers = Path(__file__).resolve().parent.parent.parent / "hooks" / "_helpers"
        sys.path.insert(0, str(helpers))
        import trajectory_autosnap

        return trajectory_autosnap

    def _insert_observation(self, conn, session_id: str, obs_type: str = "tool_failure") -> None:
        import hashlib
        import secrets

        h = hashlib.sha256(secrets.token_bytes(8)).hexdigest()[:16]
        conn.execute(
            "INSERT INTO observations "
            "(session_id, tool_name, observation_type, memory_type, impact_score, "
            " title, narrative, content_hash, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))",
            (
                session_id,
                "Edit",
                obs_type,
                "hook_block",
                0.6,
                "Tool failure: Edit",
                "BLOCKED: bad pattern",
                h,
            ),
        )
        conn.commit()

    def test_below_threshold_no_backtrack(self, conn):
        mod = self._import_autosnap()
        self._insert_observation(conn, "sess-agg-01")
        mod._aggregate_tool_failures(conn, "sess-agg-01")
        row = conn.execute(
            "SELECT 1 FROM backtrack_events WHERE session_id='sess-agg-01' "
            "AND root_cause='tool_failure'"
        ).fetchone()
        assert row is None

    def test_at_threshold_creates_backtrack(self, conn):
        mod = self._import_autosnap()
        self._insert_observation(conn, "sess-agg-02")
        self._insert_observation(conn, "sess-agg-02")
        mod._aggregate_tool_failures(conn, "sess-agg-02")
        row = conn.execute(
            "SELECT root_cause, reason FROM backtrack_events "
            "WHERE session_id='sess-agg-02' AND root_cause='tool_failure'"
        ).fetchone()
        assert row is not None
        assert "Auto-aggregated" in row["reason"]
        assert "2 tool failures" in row["reason"]

    def test_idempotent_second_call_no_duplicate(self, conn):
        mod = self._import_autosnap()
        for _ in range(3):
            self._insert_observation(conn, "sess-agg-03")
        mod._aggregate_tool_failures(conn, "sess-agg-03")
        mod._aggregate_tool_failures(conn, "sess-agg-03")  # second call
        count = conn.execute(
            "SELECT COUNT(*) FROM backtrack_events WHERE session_id='sess-agg-03' "
            "AND root_cause='tool_failure'"
        ).fetchone()[0]
        assert count == 1

    def test_other_observation_types_not_counted(self, conn):
        mod = self._import_autosnap()
        self._insert_observation(conn, "sess-agg-04", obs_type="success")
        self._insert_observation(conn, "sess-agg-04", obs_type="discovery")
        mod._aggregate_tool_failures(conn, "sess-agg-04")
        row = conn.execute(
            "SELECT 1 FROM backtrack_events WHERE session_id='sess-agg-04' "
            "AND root_cause='tool_failure'"
        ).fetchone()
        assert row is None


# ---------------------------------------------------------------------------
# Gap A — trajectory_autosnap derive_snapshot + write_snapshot
# ---------------------------------------------------------------------------


class TestAutosnap:
    """Tests for trajectory_autosnap.py derive_snapshot end-to-end."""

    def _import_autosnap(self):
        helpers = Path(__file__).resolve().parent.parent.parent / "hooks" / "_helpers"
        sys.path.insert(0, str(helpers))
        import importlib

        import trajectory_autosnap

        importlib.reload(trajectory_autosnap)
        return trajectory_autosnap

    def _insert_formula_dispatch(self, conn, session_id: str, formula_id: str) -> None:
        conn.execute(
            "INSERT INTO formula_dispatches "
            "(session_id, persona_id, formula_id, input_hash, status, ts) "
            "VALUES (?, '', ?, '', 'ok', datetime('now'))",
            (session_id, formula_id),
        )
        conn.commit()

    def _insert_backtrack(self, conn, session_id: str, root_cause: str | None = None) -> None:
        conn.execute(
            "INSERT INTO backtrack_events "
            "(session_id, from_formula, to_formula, reason, ts, root_cause) "
            "VALUES (?, '', '', 'test', datetime('now'), ?)",
            (session_id, root_cause),
        )
        conn.commit()

    def test_derive_snapshot_basic(self, conn):
        mod = self._import_autosnap()
        sid = "snap-sess-01"
        self._insert_formula_dispatch(conn, sid, "implementer.code")
        snap = mod.derive_snapshot(conn, sid)
        assert snap is not None
        assert "implementation" in snap["current_focus"]
        assert snap["confidence"] > 0

    def test_derive_snapshot_with_backtracks_lowers_confidence(self, conn):
        mod = self._import_autosnap()
        sid = "snap-sess-02"
        for _ in range(4):
            self._insert_backtrack(conn, sid, "scope_too_large")
        snap = mod.derive_snapshot(conn, sid)
        assert snap["confidence"] < 0.9

    def test_derive_snapshot_anti_patterns_from_root_causes(self, conn):
        mod = self._import_autosnap()
        sid = "snap-sess-03"
        self._insert_backtrack(conn, sid, "missing_context")
        snap = mod.derive_snapshot(conn, sid)
        assert any(p["pattern"] == "missing_context" for p in snap["anti_patterns_discovered"])

    def test_derive_snapshot_next_step_hint(self, conn):
        mod = self._import_autosnap()
        sid = "snap-sess-04"
        self._insert_backtrack(conn, sid, "tool_failure")
        snap = mod.derive_snapshot(conn, sid)
        assert "verify permissions" in snap["next_logical_step"]

    def test_idempotent_double_call(self, conn):
        mod = self._import_autosnap()
        sid = "snap-sess-05"
        self._insert_formula_dispatch(conn, sid, "researcher.docs")
        snap1 = mod.derive_snapshot(conn, sid)
        mod.write_snapshot(conn, snap1)
        snap2 = mod.derive_snapshot(conn, sid)
        assert snap2 is None  # already snapped

    def test_write_snapshot_sets_supersedes_id(self, conn):
        mod = self._import_autosnap()
        snap_a = {
            "session_id": "snap-chain-01",
            "phase": "alpha",
            "current_focus": "implementation",
            "architectural_decisions": [],
            "anti_patterns_discovered": [],
            "open_questions": [],
            "next_logical_step": "",
            "confidence": 0.8,
        }
        snap_b = {
            "session_id": "snap-chain-02",
            "phase": "beta",
            "current_focus": "review",
            "architectural_decisions": [],
            "anti_patterns_discovered": [],
            "open_questions": [],
            "next_logical_step": "",
            "confidence": 0.9,
        }
        id_a = mod.write_snapshot(conn, snap_a)
        id_b = mod.write_snapshot(conn, snap_b)
        row = conn.execute(
            "SELECT supersedes_id FROM project_trajectory WHERE id=?", (id_b,)
        ).fetchone()
        assert row["supersedes_id"] == id_a


# ---------------------------------------------------------------------------
# Gap C — mid-session adaptation in cos_backtrack_log
# ---------------------------------------------------------------------------


class TestMidSessionAdaptation:
    """Tests for suggested_action returned by cos_backtrack_log."""

    def _make_backtrack_tool(self, db_path: Path):
        from unittest.mock import MagicMock

        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from tools.cognition import register_cos_backtrack_log

        mcp = MagicMock()
        captured = {}

        def tool_decorator(**kwargs):
            def inner(fn):
                captured["fn"] = fn
                return fn

            return inner

        mcp.tool = tool_decorator
        register_cos_backtrack_log(mcp, str(db_path))
        raw_fn = captured["fn"]

        # @safe_tool returns JSON string — wrap to return parsed dict
        def fn(**kwargs):
            return json.loads(raw_fn(**kwargs))

        return fn

    def test_backtrack_with_root_cause_returns_suggested_action(self, db_path):
        fn = self._make_backtrack_tool(db_path)
        result = fn(
            session_id="c-sess-01",
            from_formula="implementer",
            to_formula="researcher",
            reason="Lacked context to proceed",
            root_cause="missing_context",
        )
        data = result.get("data", {})
        assert "suggested_action" in data
        assert data["suggested_action"]  # non-empty

    def test_backtrack_missing_context_action_content(self, db_path):
        fn = self._make_backtrack_tool(db_path)
        result = fn(
            session_id="c-sess-02",
            from_formula="implementer",
            to_formula="researcher",
            reason="Need more docs",
            root_cause="missing_context",
        )
        action = result["data"]["suggested_action"]
        assert "cos_doc_search" in action or "doc" in action.lower()

    def test_backtrack_scope_too_large_action(self, db_path):
        fn = self._make_backtrack_tool(db_path)
        result = fn(
            session_id="c-sess-03",
            from_formula="implementer",
            to_formula="architect",
            reason="Task too wide",
            root_cause="scope_too_large",
        )
        action = result["data"]["suggested_action"]
        assert action  # non-empty, scope guidance

    def test_backtrack_without_root_cause_no_suggested_action(self, db_path):
        fn = self._make_backtrack_tool(db_path)
        result = fn(
            session_id="c-sess-04",
            from_formula="implementer",
            to_formula="debugger",
            reason="Something went wrong",
        )
        data = result.get("data", {})
        # suggested_action absent or empty when root_cause not given
        assert data.get("suggested_action", "") == ""

    def test_backtrack_root_cause_summary_in_response(self, db_path):
        fn = self._make_backtrack_tool(db_path)
        for _ in range(2):
            fn(
                session_id="c-sess-05",
                from_formula="implementer",
                to_formula="researcher",
                reason="Context missing",
                root_cause="missing_context",
            )
        result = fn(
            session_id="c-sess-05",
            from_formula="implementer",
            to_formula="architect",
            reason="Another context issue",
            root_cause="missing_context",
        )
        data = result["data"]
        assert "root_cause_summary" in data
        summary = data["root_cause_summary"]
        assert isinstance(summary, dict)
        assert "missing_context" in summary
