"""
Tests for the agent-dispatcher Protocol, factory, and both implementations.

Covers:
  - Protocol runtime-checkable shape
  - Factory detection by env vars (COS_AGENT, COS_AGENT_DIR, FORCE_DEFAULT)
  - DefaultDispatcher returns skipped/inline-dispatch-required
  - ClaudeSDKDispatcher availability probe
  - ClaudeSDKDispatcher happy-path (mocked query)
  - ClaudeSDKDispatcher timeout path (mocked slow query)
  - ClaudeSDKDispatcher missing-json handling
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest

# Ensure core/thinking_os on sys.path
_HERE = Path(__file__).resolve().parent
_CORE_TOS = _HERE.parent
if str(_CORE_TOS) not in sys.path:
    sys.path.insert(0, str(_CORE_TOS))

from dispatcher import (  # noqa: E402
    AgentDispatcher,
    DispatchRequest,
    DispatchResult,
    get_dispatcher,
)
from dispatchers.default import DefaultDispatcher  # noqa: E402


# ---------------------------------------------------------------------------
# Protocol shape
# ---------------------------------------------------------------------------

def test_default_dispatcher_satisfies_protocol():
    d = DefaultDispatcher()
    assert isinstance(d, AgentDispatcher)
    assert d.name == "default"
    assert d.available() is True


def test_dispatch_request_roundtrip():
    req = DispatchRequest(
        formula_id="F5",
        agent_file="core/thinking_os/agents/F5_implement.md",
        prompt="implement feature X",
        input_slice={"task_description": "add-dispatcher"},
        persona_id=None,
        intensity="standard",
    )
    assert req.formula_id == "F5"
    assert req.timeout_s == 300.0


# ---------------------------------------------------------------------------
# DefaultDispatcher behaviour
# ---------------------------------------------------------------------------

def test_default_dispatcher_returns_skipped():
    d = DefaultDispatcher()
    req = DispatchRequest(
        formula_id="F2",
        agent_file="core/thinking_os/agents/F2_decompose.md",
        prompt="decompose the task",
    )
    result = asyncio.run(d.dispatch(req))
    assert isinstance(result, DispatchResult)
    assert result.status == "skipped"
    assert result.dispatcher_name == "default"
    assert result.error == "inline-dispatch-required"
    assert result.output_json["formula_id"] == "F2"
    assert "dispatch_hint" in result.output_json


# ---------------------------------------------------------------------------
# Factory detection
# ---------------------------------------------------------------------------

def test_factory_force_default(monkeypatch):
    monkeypatch.setenv("COS_FORCE_DEFAULT_DISPATCHER", "1")
    monkeypatch.setenv("COS_AGENT", "claude")
    d = get_dispatcher()
    assert d.name == "default"


def test_factory_codex_falls_back_to_default(monkeypatch):
    monkeypatch.delenv("COS_FORCE_DEFAULT_DISPATCHER", raising=False)
    monkeypatch.setenv("COS_AGENT", "codex")
    d = get_dispatcher()
    assert d.name == "default"


def test_factory_unknown_agent_falls_back(monkeypatch):
    monkeypatch.delenv("COS_FORCE_DEFAULT_DISPATCHER", raising=False)
    monkeypatch.setenv("COS_AGENT", "mystery-agent")
    d = get_dispatcher()
    assert d.name == "default"


def test_factory_reads_agent_dir(monkeypatch, tmp_path):
    monkeypatch.delenv("COS_FORCE_DEFAULT_DISPATCHER", raising=False)
    monkeypatch.delenv("COS_AGENT", raising=False)
    codex_dir = tmp_path / "codex"
    codex_dir.mkdir()
    monkeypatch.setenv("COS_AGENT_DIR", str(codex_dir))
    d = get_dispatcher()
    assert d.name == "default"


# ---------------------------------------------------------------------------
# ClaudeSDKDispatcher — availability + mocked dispatch
# ---------------------------------------------------------------------------

def _import_claude_sdk_dispatcher_module():
    """Load adapters/claude/sdk_dispatcher.py by path (same way factory does)."""
    import importlib.util
    adapter_path = (
        _CORE_TOS.parent.parent / "adapters" / "claude" / "sdk_dispatcher.py"
    )
    spec = importlib.util.spec_from_file_location(
        "_test_claude_sdk_dispatcher", adapter_path,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_claude_sdk_dispatcher_availability():
    mod = _import_claude_sdk_dispatcher_module()
    d = mod.ClaudeSDKDispatcher()
    # May be True or False depending on install, but must be boolean
    assert d.available() in (True, False)
    assert d.name == "claude-sdk"


@pytest.mark.skipif(
    os.environ.get("COS_SKIP_SDK_TESTS") == "1",
    reason="claude-sdk tests disabled",
)
def test_claude_sdk_dispatcher_happy_path(monkeypatch, tmp_path):
    """Mock the SDK's query() to yield a canned AssistantMessage with JSON."""
    mod = _import_claude_sdk_dispatcher_module()
    d = mod.ClaudeSDKDispatcher()
    if not d.available():
        pytest.skip("claude-agent-sdk not installed")

    # Write a tiny agent file
    agent_file = tmp_path / "F99_test.md"
    agent_file.write_text(
        "---\nid: F99\nname: test\n---\n\nTest formula body."
    )

    # Build fake message objects matching the SDK's shape
    from claude_agent_sdk import AssistantMessage, TextBlock

    fake_text = 'Here is my output:\n```json\n{"decomposition":"ok","actors":["a"]}\n```'
    fake_msg = AssistantMessage(content=[TextBlock(text=fake_text)], model="test")

    async def fake_query(prompt, options):
        yield fake_msg

    # Patch the SDK query function in the dispatcher's import scope
    import claude_agent_sdk as sdk_module
    monkeypatch.setattr(sdk_module, "query", fake_query)

    req = DispatchRequest(
        formula_id="F99",
        agent_file=str(agent_file),
        prompt="decompose",
        input_slice={"task_description": "test"},
    )
    result = asyncio.run(d.dispatch(req))

    assert result.status == "ok", f"expected ok, got: {result.error!r}"
    assert result.output_json.get("decomposition") == "ok"
    assert result.output_json.get("actors") == ["a"]
    assert result.dispatcher_name == "claude-sdk"
    assert result.latency_ms >= 0


@pytest.mark.skipif(
    os.environ.get("COS_SKIP_SDK_TESTS") == "1",
    reason="claude-sdk tests disabled",
)
def test_claude_sdk_dispatcher_timeout(monkeypatch, tmp_path):
    mod = _import_claude_sdk_dispatcher_module()
    d = mod.ClaudeSDKDispatcher()
    if not d.available():
        pytest.skip("claude-agent-sdk not installed")

    agent_file = tmp_path / "F99_slow.md"
    agent_file.write_text("---\nid: F99\n---\n\nSlow formula.")

    async def slow_query(prompt, options):
        await asyncio.sleep(5)
        if False:  # keep generator typing
            yield None

    import claude_agent_sdk as sdk_module
    monkeypatch.setattr(sdk_module, "query", slow_query)

    req = DispatchRequest(
        formula_id="F99",
        agent_file=str(agent_file),
        prompt="test timeout",
        timeout_s=0.1,
    )
    result = asyncio.run(d.dispatch(req))
    assert result.status == "timeout"
    assert "timed out" in (result.error or "")


@pytest.mark.skipif(
    os.environ.get("COS_SKIP_SDK_TESTS") == "1",
    reason="claude-sdk tests disabled",
)
def test_claude_sdk_dispatcher_missing_json(monkeypatch, tmp_path):
    mod = _import_claude_sdk_dispatcher_module()
    d = mod.ClaudeSDKDispatcher()
    if not d.available():
        pytest.skip("claude-agent-sdk not installed")

    agent_file = tmp_path / "F99_noop.md"
    agent_file.write_text("---\nid: F99\n---\n\nNo-op formula.")

    from claude_agent_sdk import AssistantMessage, TextBlock

    async def fake_query(prompt, options):
        yield AssistantMessage(
            content=[TextBlock(text="I forgot to emit JSON, sorry.")],
            model="test",
        )

    import claude_agent_sdk as sdk_module
    monkeypatch.setattr(sdk_module, "query", fake_query)

    req = DispatchRequest(
        formula_id="F99",
        agent_file=str(agent_file),
        prompt="plz",
    )
    result = asyncio.run(d.dispatch(req))
    assert result.status == "error"
    assert "no JSON block" in (result.error or "")
