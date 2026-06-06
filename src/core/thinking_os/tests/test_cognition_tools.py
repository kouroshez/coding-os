"""Tests for MCP tools in tools/cognition.py."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

# Ensure thinking_os root is on path (same pattern as other tests in this dir)
_THINKING_OS = Path(__file__).resolve().parent.parent
if str(_THINKING_OS) not in sys.path:
    sys.path.insert(0, str(_THINKING_OS))

from database import has_backtrack_events_table, has_formula_dispatches_table, init_db

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_conn(tmp_path):
    """Fresh in-memory DB with all migrations applied."""
    conn = init_db(":memory:")
    yield conn
    conn.close()


@pytest.fixture()
def db_path(tmp_path):
    """Temporary DB file for tools that open their own connection."""
    path = str(tmp_path / "test.db")
    conn = init_db(path)
    conn.close()
    return path


class _FakeMcp:
    """Minimal FastMCP stand-in: captures registered tool functions by name."""

    def __init__(self):
        self._tools: dict = {}

    def tool(self, name: str = "", description: str = "", annotations: dict = None):
        def decorator(fn):
            self._tools[name or fn.__name__] = fn
            return fn

        return decorator

    def call(self, name: str, **kwargs) -> dict:
        result = self._tools[name](**kwargs)
        return json.loads(result)


@pytest.fixture()
def mcp_tools(db_path):
    """Register all cognition tools on a fake MCP and return the helper."""
    from tools.cognition import register_all

    fake = _FakeMcp()
    register_all(fake, db_path)
    return fake


# ---------------------------------------------------------------------------
# DB migration v14 tests
# ---------------------------------------------------------------------------


class TestV14Migration:
    def test_formula_dispatches_exists(self, db_conn):
        assert has_formula_dispatches_table(db_conn)

    def test_backtrack_events_exists(self, db_conn):
        assert has_backtrack_events_table(db_conn)

    def test_persona_selections_exists(self, db_conn):
        row = db_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='persona_selections'"
        ).fetchone()
        assert row is not None

    def test_ambiguity_violations_exists(self, db_conn):
        row = db_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='ambiguity_violations'"
        ).fetchone()
        assert row is not None

    def test_indices_exist(self, db_conn):
        names = {
            r[0]
            for r in db_conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()
        }
        assert "idx_backtrack_session" in names
        assert "idx_dispatches_session" in names


# ---------------------------------------------------------------------------
# cos_supervise
# ---------------------------------------------------------------------------


class TestCosSupervise:
    def test_idle_returns_classify(self, mcp_tools):
        result = mcp_tools.call(
            "cos_supervise",
            session_id="ses-test",
            task_marker="feat-auth",
            persona_id="junior-dev",
            phase="IDLE",
        )
        assert result["ok"] is True
        assert result["data"]["action"] == "classify"

    def test_routing_returns_dispatch(self, mcp_tools):
        result = mcp_tools.call(
            "cos_supervise",
            session_id="ses-test",
            task_marker="feat-auth",
            persona_id="chain:implementer,reviewer",
            phase="ROUTING",
        )
        assert result["data"]["action"] == "dispatch"
        assert result["data"]["formula"] is not None

    def test_done_when_all_dispatched(self, mcp_tools):
        result = mcp_tools.call(
            "cos_supervise",
            session_id="ses-test",
            task_marker="feat-auth",
            persona_id="chain:implementer,reviewer",
            phase="DISPATCHING",
            dispatched='["implementer", "reviewer"]',
            pending='["implementer", "reviewer"]',
        )
        assert result["data"]["action"] == "done"


# ---------------------------------------------------------------------------
# cos_backtrack_log
# ---------------------------------------------------------------------------


class TestCosBacktrackLog:
    def test_records_backtrack(self, mcp_tools, db_path):
        result = mcp_tools.call(
            "cos_backtrack_log",
            session_id="ses-bt-1",
            from_formula="architect",
            to_formula="analyst",
            reason="missing actor",
        )
        assert result["ok"] is True
        assert result["data"]["count"] == 1

    def test_advisory_at_3(self, mcp_tools):
        for _ in range(3):
            result = mcp_tools.call(
                "cos_backtrack_log",
                session_id="ses-bt-adv",
                from_formula="architect",
                to_formula="analyst",
                reason="test",
            )
        assert "Anti-Paralysis" in result["data"]["advisory"]


# ---------------------------------------------------------------------------
# cos_ambiguity_check
# ---------------------------------------------------------------------------


class TestCosAmbiguityCheck:
    def test_empty_bundle_passes(self, mcp_tools):
        result = mcp_tools.call(
            "cos_ambiguity_check",
            session_id="ses-amb-empty",
            task_marker="feat-auth",
            persona_id="senior-backend",
        )
        assert result["ok"] is True
        assert result["data"]["passed"] is True

    def test_f2_missing_actors_fails(self, mcp_tools, db_path):
        import json
        from pathlib import Path

        from cognition_schemas import AnalystOutput, EvidenceBundle

        # Write a bundle with missing actors to disk
        bundle = EvidenceBundle(task_marker="feat-amb", persona_id="senior-backend")
        bundle.analyst = AnalystOutput(problem_statement="Add auth", actors=[])
        agent_dir = Path(".coding-os") / "claude"
        agent_dir.mkdir(parents=True, exist_ok=True)
        bp = agent_dir / "evidence_bundle_ses-amb-missing.json"
        bp.write_text(bundle.model_dump_json())

        result = mcp_tools.call(
            "cos_ambiguity_check",
            session_id="ses-amb-missing",
            task_marker="feat-amb",
            persona_id="senior-backend",
        )
        assert result["data"]["passed"] is False
        assert len(result["data"]["violations"]) > 0

    def test_pass_clears_prior_violations(self, mcp_tools, db_path):
        # The enforce-anti-ambiguity gate reads ambiguity_violations as the
        # CURRENT state — a later passing check must clear the session's rows.
        import sqlite3
        from pathlib import Path

        from cognition_schemas import AnalystOutput, EvidenceBundle

        agent_dir = Path(".coding-os") / "claude"
        agent_dir.mkdir(parents=True, exist_ok=True)
        sid = "ses-amb-clear"

        bad = EvidenceBundle(task_marker="feat-amb", persona_id="p")
        bad.analyst = AnalystOutput(problem_statement="x", actors=[])
        (agent_dir / f"evidence_bundle_{sid}.json").write_text(bad.model_dump_json())
        r1 = mcp_tools.call(
            "cos_ambiguity_check", session_id=sid, task_marker="feat-amb", persona_id="p"
        )
        assert r1["data"]["passed"] is False
        with sqlite3.connect(db_path) as c:
            n = c.execute(
                "SELECT COUNT(*) FROM ambiguity_violations WHERE session_id=?", (sid,)
            ).fetchone()[0]
        assert n > 0

        ok_bundle = EvidenceBundle(task_marker="feat-amb", persona_id="p")
        (agent_dir / f"evidence_bundle_{sid}.json").write_text(ok_bundle.model_dump_json())
        r2 = mcp_tools.call(
            "cos_ambiguity_check", session_id=sid, task_marker="feat-amb", persona_id="p"
        )
        assert r2["data"]["passed"] is True
        with sqlite3.connect(db_path) as c:
            n2 = c.execute(
                "SELECT COUNT(*) FROM ambiguity_violations WHERE session_id=?", (sid,)
            ).fetchone()[0]
        assert n2 == 0, "passing check must clear prior violations"


# ---------------------------------------------------------------------------
# cos_situation_detect
# ---------------------------------------------------------------------------


class TestCosSituationDetect:
    def test_detects_incident_response(self, mcp_tools):
        result = mcp_tools.call(
            "cos_situation_detect",
            signals='["production_down", "pager_fired"]',
        )
        assert result["ok"] is True
        assert result["data"]["situation_id"] == "incident-response"

    def test_no_match_returns_null(self, mcp_tools):
        result = mcp_tools.call(
            "cos_situation_detect",
            signals='["unknown_signal"]',
        )
        assert result["data"]["situation_id"] is None

    def test_detects_onboarding(self, mcp_tools):
        result = mcp_tools.call(
            "cos_situation_detect",
            signals='["new_team_member"]',
        )
        assert result["data"]["situation_id"] == "onboarding"

    def test_detects_takeover(self, mcp_tools):
        result = mcp_tools.call(
            "cos_situation_detect",
            signals='["legacy_codebase", "no_docs"]',
        )
        assert result["data"]["situation_id"] == "existing-project-takeover"


# ---------------------------------------------------------------------------
# cos_classify_prompt — gate-record correctness
# ---------------------------------------------------------------------------


class TestCosClassifyPromptGateRecord:
    """Gate write must be panel-correct + session-prefixed, or honestly report
    recorded=false with a shell hint — never a wrong-dir/wrong-format fossil the
    strict panel reader (check-state.sh) would reject."""

    def test_records_panel_gate_with_session_prefix(self, mcp_tools, tmp_path, monkeypatch):
        panel = tmp_path / "panels" / "p1"
        panel.mkdir(parents=True)
        (panel / "session-id").write_text("ses-classify-1\n", encoding="utf-8")
        monkeypatch.delenv("COS_PANEL_DIR", raising=False)
        result = mcp_tools.call(
            "cos_classify_prompt",
            prompt="fix typo in readme",
            record=True,
            agent_dir=str(panel),
        )
        assert result["ok"] is True
        assert result["data"]["recorded"] is True
        gate = (panel / ".thinking_os-gate").read_text(encoding="utf-8").strip()
        parts = gate.split(" ")
        assert parts[0] == "ses-classify-1"
        assert parts[1] == result["data"]["complexity"]
        assert parts[2] == str(result["data"]["dimensions"])

    def test_no_panel_session_returns_hint(self, mcp_tools, monkeypatch):
        monkeypatch.delenv("COS_PANEL_DIR", raising=False)
        result = mcp_tools.call(
            "cos_classify_prompt",
            prompt="design a multi-service auth and payments integration strategy",
            record=True,
            agent_dir="",
        )
        assert result["ok"] is True
        assert result["data"]["recorded"] is False
        assert "write-state.sh" in result["data"]["record_hint"]
