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

from database import has_formula_dispatches_table, init_db

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


class TestV14Migration:
    def test_formula_dispatches_exists(self, db_conn):
        assert has_formula_dispatches_table(db_conn)


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
