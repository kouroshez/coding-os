"""Parity guards for the Claude session-options SSOT builder (TASK-417).

Pins the empirically-validated chat-light policy: cos_* capability via
programmatic mcp_servers, base tools kept, Write/Edit absent, destructive
Bash deny floor, setting_sources=[].
"""

import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
DISPATCHER = REPO / "src" / "adapters" / "claude" / "sdk_dispatcher.py"

pytest.importorskip("claude_agent_sdk")


def _load_module():
    spec = importlib.util.spec_from_file_location("cos_test_claude_sdk_dispatcher", DISPATCHER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_builder():
    return _load_module().claude_session_options


def _mcp_cwd(tmp_path):
    (tmp_path / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"coding-os": {"command": "cos", "args": ["server-start"]}}})
    )
    return str(tmp_path)


def test_chat_profile_capability_and_security(tmp_path):
    build = _load_builder()
    o = build(
        "chat",
        cwd=_mcp_cwd(tmp_path),
        model="claude-opus-4-8",
        system_prompt={"type": "preset", "preset": "claude_code"},
    )
    # P2 capability: cos_* registered programmatically + allow-listed
    assert "coding-os" in (o.mcp_servers or {})
    assert "mcp__coding-os__*" in o.allowed_tools
    # base tools kept — no regression (allow-list is exclusive under dontAsk)
    assert "Read" in o.allowed_tools and "Bash" in o.allowed_tools
    # chat-light: cannot mutate code
    assert "Write" not in o.allowed_tools and "Edit" not in o.allowed_tools
    # P3: destructive-Bash deny floor present
    assert any("rm -rf" in d for d in o.disallowed_tools)
    # latency-preserving + streaming
    assert o.setting_sources == []
    assert o.include_partial_messages is True
    # TASK-756: no hub-settings.json → subscription default, explicitly cleared
    assert o.env.get("ANTHROPIC_API_KEY") == ""


def test_claude_auth_env_subscription_default(tmp_path):
    """No hub-settings.json (the common case) → explicit clear, never a no-op."""
    mod = _load_module()
    assert mod._claude_auth_env(str(tmp_path)) == {"ANTHROPIC_API_KEY": ""}


def test_claude_auth_env_subscription_explicit(tmp_path):
    (tmp_path / ".coding-os").mkdir()
    (tmp_path / ".coding-os" / "hub-settings.json").write_text(
        json.dumps({"claude_auth": {"mode": "subscription", "api_key": "sk-ant-leftover"}})
    )
    mod = _load_module()
    # mode="subscription" clears the key even if one happens to be stored —
    # switching modes in the panel must not require also blanking the field.
    assert mod._claude_auth_env(str(tmp_path)) == {"ANTHROPIC_API_KEY": ""}


def test_claude_auth_env_api_key_mode(tmp_path):
    (tmp_path / ".coding-os").mkdir()
    (tmp_path / ".coding-os" / "hub-settings.json").write_text(
        json.dumps({"claude_auth": {"mode": "api_key", "api_key": "sk-ant-abc123"}})
    )
    mod = _load_module()
    assert mod._claude_auth_env(str(tmp_path)) == {"ANTHROPIC_API_KEY": "sk-ant-abc123"}


def test_claude_auth_env_api_key_mode_without_key_clears(tmp_path):
    (tmp_path / ".coding-os").mkdir()
    (tmp_path / ".coding-os" / "hub-settings.json").write_text(
        json.dumps({"claude_auth": {"mode": "api_key", "api_key": ""}})
    )
    mod = _load_module()
    assert mod._claude_auth_env(str(tmp_path)) == {"ANTHROPIC_API_KEY": ""}


def test_claude_auth_env_corrupt_settings_fails_safe(tmp_path):
    (tmp_path / ".coding-os").mkdir()
    (tmp_path / ".coding-os" / "hub-settings.json").write_text("not json")
    mod = _load_module()
    assert mod._claude_auth_env(str(tmp_path)) == {"ANTHROPIC_API_KEY": ""}


def test_chat_resume_sets_resume_and_fork(tmp_path):
    build = _load_builder()
    o = build(
        "chat_resume",
        cwd=_mcp_cwd(tmp_path),
        model=None,
        system_prompt=None,
        resume="sid-123",
        fork=True,
    )
    assert o.resume == "sid-123"
    assert o.fork_session is True
    assert "mcp__coding-os__*" in o.allowed_tools
    assert "Write" not in o.allowed_tools


def test_unmigrated_profile_raises(tmp_path):
    build = _load_builder()
    with pytest.raises(NotImplementedError):
        build("dispatch", cwd=str(tmp_path), model=None, system_prompt=None)


def test_generic_agent_options_seam(tmp_path):
    """The non-profile seam core routes its remaining builds through (TASK-472)."""
    mod = _load_module()
    o = mod.claude_agent_options(
        cwd=str(tmp_path), model=None, max_turns=7, allowed_tools=["mcp__coding-os__*"]
    )
    assert o.max_turns == 7
    assert "mcp__coding-os__*" in o.allowed_tools
