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
from pathlib import Path

from thinking_os.dispatcher import (
    AgentDispatcher,
    DispatchRequest,
    DispatchResult,
    get_dispatcher,
)
from thinking_os.dispatchers.default import DefaultDispatcher

_CORE_TOS = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Protocol shape
# ---------------------------------------------------------------------------


def _import_codex_sdk_dispatcher_module():
    """Load adapters/codex/sdk_dispatcher.py by path (same way factory does)."""
    import importlib.util

    adapter_path = _CORE_TOS.parent.parent / "adapters" / "codex" / "sdk_dispatcher.py"
    spec = importlib.util.spec_from_file_location(
        "_test_codex_sdk_dispatcher",
        adapter_path,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _codex_jsonl(payload: dict) -> str:
    import json

    return "\n".join(
        [
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {
                        "type": "agent_message",
                        "text": f"```json\n{json.dumps(payload)}\n```",
                    },
                }
            ),
            json.dumps({"type": "turn.completed", "usage": {"input_tokens": 10}}),
        ]
    )


def test_default_dispatcher_satisfies_protocol():
    d = DefaultDispatcher()
    assert isinstance(d, AgentDispatcher)
    assert d.name == "default"
    assert d.available() is True


def test_dispatch_request_roundtrip():
    req = DispatchRequest(
        formula_id="implementer",
        agent_file="src/core/thinking_os/agents/implementer.md",
        prompt="implement feature X",
        input_slice={"task_description": "add-dispatcher"},
        persona_id=None,
        intensity="standard",
    )
    assert req.formula_id == "implementer"
    assert req.timeout_s == 300.0


def test_default_dispatcher_returns_skipped():
    d = DefaultDispatcher()
    req = DispatchRequest(
        formula_id="analyst",
        agent_file="src/core/thinking_os/agents/analyst.md",
        prompt="decompose the task",
    )
    result = asyncio.run(d.dispatch(req))
    assert isinstance(result, DispatchResult)
    assert result.status == "skipped"
    assert result.dispatcher_name == "default"
    assert result.error == "inline-dispatch-required"
    assert result.output_json["formula_id"] == "analyst"
    assert "dispatch_hint" in result.output_json


def test_factory_force_default(monkeypatch):
    monkeypatch.setenv("COS_FORCE_DEFAULT_DISPATCHER", "1")
    monkeypatch.setenv("COS_AGENT", "claude")
    d = get_dispatcher()
    assert d.name == "default"


def test_factory_codex_falls_back_to_default_when_binary_absent(monkeypatch):
    """When `codex` binary is not in PATH, factory returns default."""
    import shutil

    monkeypatch.delenv("COS_FORCE_DEFAULT_DISPATCHER", raising=False)
    monkeypatch.setenv("COS_AGENT", "codex")
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    d = get_dispatcher()
    assert d.name == "default"


def test_factory_codex_returns_codex_sdk_when_binary_present(monkeypatch):
    """When `codex` binary is found, factory returns codex-sdk dispatcher."""
    import shutil

    monkeypatch.delenv("COS_FORCE_DEFAULT_DISPATCHER", raising=False)
    monkeypatch.setenv("COS_AGENT", "codex")
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/codex" if name == "codex" else None)
    d = get_dispatcher()
    assert d.name == "codex-sdk"


def test_factory_unknown_agent_falls_back(monkeypatch):
    monkeypatch.delenv("COS_FORCE_DEFAULT_DISPATCHER", raising=False)
    monkeypatch.setenv("COS_AGENT", "mystery-agent")
    d = get_dispatcher()
    assert d.name == "default"


def test_factory_reads_agent_dir(monkeypatch, tmp_path):
    import shutil

    monkeypatch.delenv("COS_FORCE_DEFAULT_DISPATCHER", raising=False)
    monkeypatch.delenv("COS_AGENT", raising=False)
    # Ensure no codex binary so codex-sdk doesn't intercept.
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    codex_dir = tmp_path / "codex"
    codex_dir.mkdir()
    monkeypatch.setenv("COS_AGENT_DIR", str(codex_dir))
    d = get_dispatcher()
    assert d.name == "default"
