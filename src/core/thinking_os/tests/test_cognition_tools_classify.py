"""Tests for MCP tools in tools/cognition.py."""

from __future__ import annotations

import json
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


class TestCosClassifyPromptCognitionNudge:
    """A COMPLICATED+ gate with the cognition module disabled (lean profile)
    surfaces a discoverability nudge to re-enable it, instead of letting the
    agent hit a module_disabled wall on cos_compose_chain mid-plan (TASK-509)."""

    _COMPLEX = "design a multi-service auth and payments integration strategy"

    def test_nudge_when_cognition_disabled(self, mcp_tools, tmp_path, monkeypatch):
        import json as _json

        state = tmp_path / ".coding-os"
        state.mkdir(parents=True)
        (state / "subsystems-state.json").write_text(
            _json.dumps({"version": 1, "disabled": ["cognition"]}), encoding="utf-8"
        )
        monkeypatch.setenv("COS_STATE_DIR", str(state))
        result = mcp_tools.call("cos_classify_prompt", prompt=self._COMPLEX, record=False)
        assert result["ok"] is True
        assert result["data"]["complexity"] in ("COMPLICATED", "COMPLEX")
        assert "cos module enable cognition" in result["data"]["nudge"]

    def test_no_nudge_when_cognition_enabled(self, mcp_tools, tmp_path, monkeypatch):
        monkeypatch.setenv("COS_STATE_DIR", str(tmp_path / "absent"))  # no state = all on
        result = mcp_tools.call("cos_classify_prompt", prompt=self._COMPLEX, record=False)
        assert result["ok"] is True
        assert result["data"]["nudge"] == ""
