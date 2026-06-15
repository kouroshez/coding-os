"""Tests for board_os._agent_runtime (Wave 0 E2)."""

from __future__ import annotations

import os

import pytest

from core.board_os import _agent_runtime as ar


@pytest.fixture(autouse=True)
def _scrub_env(tmp_path, monkeypatch):
    """Clear all known env markers + run from a clean cwd."""
    for k in (
        "COS_AGENT",
        "COS_HUMAN_ACTOR",
        "COS_STATE_DIR",
        "CLAUDECODE",
        "CLAUDE_CODE_SSE_PORT",
        "CLAUDE_CODE_ENTRYPOINT",
        "CLAUDE_AGENT_SDK_VERSION",
        "CODEX_SESSION_ID",
        "CODEX_AGENT_DIR",
        "CODEX_HOME",
    ):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.chdir(tmp_path)
    ar.reset_cache()
    yield
    ar.reset_cache()


def test_explicit_session_matches_known_id():
    assert ar.detect_agent("ses-claude-abc") == "claude"
    assert ar.detect_agent("ses-codex-9") == "codex"


def test_explicit_session_human():
    assert ar.detect_agent("human-pair") == "human"


def test_cos_agent_env_override(monkeypatch):
    monkeypatch.setenv("COS_AGENT", "codex")
    assert ar.detect_agent(None) == "codex"


def test_cos_agent_env_unknown_falls_through(monkeypatch):
    monkeypatch.setenv("COS_AGENT", "made-up")
    # Falls through to vendor markers — none set, then to fallback "agent".
    assert ar.detect_agent(None) == "agent"


def test_vendor_marker_claude(monkeypatch):
    monkeypatch.setenv("CLAUDECODE", "1")
    assert ar.detect_agent(None) == "claude"


def test_vendor_marker_codex(monkeypatch):
    monkeypatch.setenv("CODEX_SESSION_ID", "ses-codex-1")
    assert ar.detect_agent(None) == "codex"


def test_marker_file_fallback(tmp_path, monkeypatch):
    state_dir = tmp_path / ".coding-os"
    state_dir.mkdir()
    (state_dir / ".agent").write_text("codex\n")
    monkeypatch.setenv("COS_STATE_DIR", str(state_dir))
    assert ar.detect_agent(None) == "codex"


def test_unknown_falls_back_to_agent_literal():
    # No env, no marker file, no explicit session → "agent" sentinel.
    assert ar.detect_agent(None) == "agent"


def test_explicit_overrides_env(monkeypatch):
    monkeypatch.setenv("CLAUDECODE", "1")
    assert ar.detect_agent("ses-codex-x") == "codex"


def test_legacy_agent_label_delegates():
    """board_os.mcp_tools._agent_label must delegate to detect_agent."""
    from core.board_os.mcp_tools import _agent_label

    assert _agent_label("ses-codex-q") == "codex"


def test_human_actor_default():
    """No auth + no override → the structured 'human' default."""
    assert ar.human_actor() == {"type": "human", "id": "human", "label": "human"}


def test_human_actor_env_id_only(monkeypatch):
    monkeypatch.setenv("COS_HUMAN_ACTOR", "u-42")
    actor = ar.human_actor()
    assert actor["type"] == "human"
    assert actor["id"] == "u-42"
    assert actor["label"] == "u-42"


def test_human_actor_env_id_and_label(monkeypatch):
    """Future-auth shape: 'id:Label' resolves both fields."""
    monkeypatch.setenv("COS_HUMAN_ACTOR", "u-42:Kourosh")
    assert ar.human_actor() == {"type": "human", "id": "u-42", "label": "Kourosh"}


# ---------- resolve_agent_session: MCP-server attribution ----------


def test_resolve_prefers_active_session_pointer_over_synthetic(tmp_path, monkeypatch):
    """MCP-server context: no per-panel $COS_SESSION_FILE, but the agent-level
    .active-session pointer names the calling panel — it must win over the
    ses-<agent>-pid<server-pid> synthetic fallback."""
    agent_dir = tmp_path / "claude"
    agent_dir.mkdir()
    (agent_dir / ".active-session").write_text("ses-claude-20260605-PANEL-A\n")
    monkeypatch.delenv("COS_SESSION_FILE", raising=False)
    monkeypatch.delenv("COS_SESSION_ID", raising=False)
    monkeypatch.setenv("COS_AGENT_DIR", str(agent_dir))
    assert ar.resolve_agent_session(None) == "ses-claude-20260605-PANEL-A"


def test_resolve_explicit_beats_active_session_pointer(tmp_path, monkeypatch):
    agent_dir = tmp_path / "claude"
    agent_dir.mkdir()
    (agent_dir / ".active-session").write_text("ses-claude-PANEL-A\n")
    monkeypatch.setenv("COS_AGENT_DIR", str(agent_dir))
    assert ar.resolve_agent_session("ses-claude-PANEL-B") == "ses-claude-PANEL-B"


def test_resolve_session_file_beats_active_session_pointer(tmp_path, monkeypatch):
    """A real per-panel $COS_SESSION_FILE (hook lineage) still wins over the
    shared agent-level pointer."""
    agent_dir = tmp_path / "claude"
    agent_dir.mkdir()
    (agent_dir / ".active-session").write_text("ses-claude-PANEL-A\n")
    session_file = tmp_path / "panels" / "B" / "session-id"
    session_file.parent.mkdir(parents=True)
    session_file.write_text("ses-claude-PANEL-B\n")
    monkeypatch.setenv("COS_AGENT_DIR", str(agent_dir))
    monkeypatch.setenv("COS_SESSION_FILE", str(session_file))
    assert ar.resolve_agent_session(None) == "ses-claude-PANEL-B"
