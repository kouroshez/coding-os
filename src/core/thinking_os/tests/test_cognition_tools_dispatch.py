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

from database import init_db

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

    def tool(self, name: str = "", description: str = "", annotations: dict | None = None):
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


class TestDispatchPersistenceDegradedPath:
    """Audit pass-4 #8: the schema-validation-failure branch of
    _persist_dispatch_output referenced an undefined `field_map`, so a real
    dispatched role returning ok-but-invalid output raised NameError (masked by
    @safe_tool as an opaque fail('internal')) instead of returning the degraded
    bundle filled-count the supervisor consumes."""

    def test_validation_failure_returns_count_not_nameerror(self, db_path):
        from tools.cognition import _persist_dispatch_output

        # 'researcher' is in ROLE_OUTPUT_CLASSES and ResearcherOutput requires
        # `summary`, so an empty output_json fails model_validate -> the degraded
        # branch (the formerly-crashing line) runs.
        filled = _persist_dispatch_output(
            session_id="sess-pass4-8",
            task_marker="TASK-470",
            persona_id="p1",
            formula_id="researcher",
            output_json={},
            status="ok",
            latency_ms=5,
            db_path=db_path,
        )
        assert isinstance(filled, int)  # returned cleanly — no NameError

    def test_validation_failure_skips_dispatch_row(self, db_path):
        from tools.cognition import _persist_dispatch_output

        _persist_dispatch_output(
            session_id="sess-pass4-8b",
            task_marker="TASK-470",
            persona_id="p1",
            formula_id="researcher",
            output_json={},
            status="ok",
            latency_ms=5,
            db_path=db_path,
        )
        with sqlite3.connect(db_path) as conn:
            rows = conn.execute(
                "SELECT COUNT(*) FROM formula_dispatches WHERE session_id = ?",
                ("sess-pass4-8b",),
            ).fetchone()[0]
        assert rows == 0  # invalid output is never persisted (T1.6)


class TestDispatchTranscriptPersistence:
    """A dispatched sub-agent's raw_transcript is persisted (migration v44) so
    its chat/session is auditable, not just its summarized output (TASK-628)."""

    def test_raw_transcript_is_stored_and_retrievable(self, db_path):
        from tools.cognition import _persist_dispatch_output

        # free-form id → no output schema → no validation → row is inserted.
        _persist_dispatch_output(
            session_id="sess-tx-1",
            task_marker="TASK-628",
            persona_id="p1",
            formula_id="free-form-xyz",
            output_json={"ok": True},
            status="ok",
            latency_ms=7,
            db_path=db_path,
            raw_transcript="USER: hi\nAGENT: done",
        )
        with sqlite3.connect(db_path) as conn:
            tx = conn.execute(
                "SELECT raw_transcript FROM formula_dispatches WHERE session_id = ?",
                ("sess-tx-1",),
            ).fetchone()[0]
        assert tx == "USER: hi\nAGENT: done"

    def test_transcript_is_null_when_absent(self, db_path):
        from tools.cognition import _persist_dispatch_output

        _persist_dispatch_output(
            session_id="sess-tx-2",
            task_marker="TASK-628",
            persona_id="p1",
            formula_id="free-form-xyz",
            output_json={"ok": True},
            status="ok",
            latency_ms=7,
            db_path=db_path,
        )
        with sqlite3.connect(db_path) as conn:
            tx = conn.execute(
                "SELECT raw_transcript FROM formula_dispatches WHERE session_id = ?",
                ("sess-tx-2",),
            ).fetchone()[0]
        assert tx is None


class TestSupervisionConfig:
    def test_show_returns_complete_default_policy(
        self, mcp_tools, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / ".coding-os").mkdir()
        monkeypatch.setenv("COS_PROJECT_ROOT", str(tmp_path))

        result = mcp_tools.call("cos_supervision_config", action="show")

        assert result["ok"] is True
        assert result["data"]["policy"]["enabled"] is False
        assert result["data"]["policy"]["cooldown"]["default_seconds"] == 300

    def test_enable_and_set_round_trip_without_hub(
        self, mcp_tools, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        state = tmp_path / ".coding-os"
        state.mkdir()
        (state / "hub-settings.json").write_text('{"foreign":{"keep":true}}', encoding="utf-8")
        monkeypatch.setenv("COS_PROJECT_ROOT", str(tmp_path))

        enabled = mcp_tools.call("cos_supervision_config", action="enable")
        configured = mcp_tools.call(
            "cos_supervision_config",
            action="set",
            mode="adaptive",
            role="reviewer",
            role_adapter="codex",
            # codex declares model_selection with an empty catalog (any string
            # forwards); it declares no effort_selection, so effort is rejected.
            role_model="gpt-5-codex",
        )

        assert enabled["data"]["policy"]["enabled"] is True
        assert configured["data"]["policy"]["mode"] == "adaptive"
        assert configured["data"]["policy"]["roles"]["reviewer"]["adapter"] == "codex"
        stored = json.loads((state / "hub-settings.json").read_text(encoding="utf-8"))
        assert stored["foreign"] == {"keep": True}

    def test_unsatisfiable_role_target_returns_validation_envelope(
        self, mcp_tools, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / ".coding-os").mkdir()
        monkeypatch.setenv("COS_PROJECT_ROOT", str(tmp_path))

        result = mcp_tools.call(
            "cos_supervision_config",
            action="set",
            role="reviewer",
            role_adapter="codex",
            role_effort="high",
        )

        assert result["ok"] is False
        assert result["error"]["category"] == "validation"
        assert "is not supported" in result["error"]["message"]

    def test_clear_flags_reject_conflicting_values(
        self, mcp_tools, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / ".coding-os").mkdir()
        monkeypatch.setenv("COS_PROJECT_ROOT", str(tmp_path))

        # The model id is irrelevant here — the conflict is rejected before any
        # descriptor lookup — so keep it a placeholder rather than a real id.
        for kwargs in (
            {"role": "reviewer", "clear_role": True, "role_model": "any-model"},
            {"clear_orchestrator": True, "orchestrator_model": "any-model"},
        ):
            result = mcp_tools.call("cos_supervision_config", action="set", **kwargs)

            assert result["ok"] is False
            assert result["error"]["category"] == "validation"

    def test_invalid_action_returns_validation_envelope(self, mcp_tools) -> None:
        result = mcp_tools.call("cos_supervision_config", action="unknown")

        assert result["ok"] is False
        assert result["error"]["category"] == "validation"

    def test_invalid_cooldown_returns_validation_envelope(
        self, mcp_tools, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / ".coding-os").mkdir()
        monkeypatch.setenv("COS_PROJECT_ROOT", str(tmp_path))

        result = mcp_tools.call(
            "cos_supervision_config",
            action="set",
            cooldown_default_seconds=600,
            cooldown_maximum_seconds=300,
        )

        assert result["ok"] is False
        assert result["error"]["category"] == "validation"
        assert "maximum_seconds must be greater" in result["error"]["message"]
