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
    DispatchRequest,
)

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


def test_codex_sdk_dispatcher_name():
    mod = _import_codex_sdk_dispatcher_module()
    d = mod.CodexSDKDispatcher()
    assert d.name == "codex-sdk"


def test_codex_sdk_dispatcher_unavailable_when_no_binary(monkeypatch):
    import shutil

    monkeypatch.setattr(shutil, "which", lambda _: None)
    mod = _import_codex_sdk_dispatcher_module()
    monkeypatch.setattr(mod, "_python_sdk_available", lambda: False)
    d = mod.CodexSDKDispatcher()
    assert d.available() is False


def test_codex_sdk_dispatcher_available_when_binary_present(monkeypatch):
    import shutil

    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/codex" if name == "codex" else None)
    mod = _import_codex_sdk_dispatcher_module()
    d = mod.CodexSDKDispatcher()
    assert d.available() is True


def test_codex_sdk_dispatcher_available_with_python_sdk_only(monkeypatch):
    import shutil

    monkeypatch.setenv("COS_CODEX_DISPATCH_BACKEND", "python-sdk")
    monkeypatch.setattr(shutil, "which", lambda _: None)
    mod = _import_codex_sdk_dispatcher_module()
    monkeypatch.setattr(mod, "_python_sdk_available", lambda: True)
    assert mod.CodexSDKDispatcher().available() is True


def test_codex_sdk_dispatcher_error_when_unavailable(monkeypatch, tmp_path):
    """dispatch() returns error result when binary absent."""
    import shutil

    monkeypatch.setattr(shutil, "which", lambda _: None)
    mod = _import_codex_sdk_dispatcher_module()
    monkeypatch.setattr(mod, "_python_sdk_available", lambda: False)
    d = mod.CodexSDKDispatcher()
    agent_file = tmp_path / "F1_test.md"
    agent_file.write_text("---\nid: F1\n---\n\nTest.")
    req = DispatchRequest(
        formula_id="researcher",
        agent_file=str(agent_file),
        prompt="test",
    )
    result = asyncio.run(d.dispatch(req))
    assert result.status == "error"
    assert result.dispatcher_name == "codex-sdk"
    assert "not in PATH" in (result.error or "")


def test_codex_sdk_dispatcher_mocked_success(monkeypatch, tmp_path):
    import shutil
    import subprocess

    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/codex" if name == "codex" else None)
    mod = _import_codex_sdk_dispatcher_module()
    d = mod.CodexSDKDispatcher()

    captured: dict = {}

    class FakeResult:
        returncode = 0
        stdout = _codex_jsonl({"summary": "done", "risks": []})
        stderr = ""

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return FakeResult()

    monkeypatch.setattr(subprocess, "run", fake_run)

    agent_file = tmp_path / "F2_test.md"
    agent_file.write_text("---\nid: F2\n---\n\nTest formula.")
    req = DispatchRequest(
        formula_id="analyst",
        agent_file=str(agent_file),
        prompt="analyse",
        input_slice={"task": "review"},
    )
    result = asyncio.run(d.dispatch(req))
    assert result.status == "ok"
    assert result.output_json.get("summary") == "done"
    assert result.dispatcher_name == "codex-sdk"
    assert result.latency_ms >= 0
    assert captured["cmd"][:4] == ["/usr/bin/codex", "--ask-for-approval", "never", "exec"]
    assert "--json" in captured["cmd"]
    assert "--ephemeral" in captured["cmd"]
    assert "--ignore-user-config" in captured["cmd"]
    assert captured["cmd"][captured["cmd"].index("--disable") + 1] == "hooks"
    config_at = captured["cmd"].index("--config")
    assert captured["cmd"][config_at + 1] == "mcp_servers={}"
    assert captured["cmd"][-1] == "-"
    assert "analyse" in captured["kwargs"]["input"]
    assert '"task": "review"' in captured["kwargs"]["input"]


def test_codex_sdk_dispatcher_mocked_timeout(monkeypatch, tmp_path):
    """Mock subprocess.run raising TimeoutExpired."""
    import shutil
    import subprocess

    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/codex" if name == "codex" else None)
    mod = _import_codex_sdk_dispatcher_module()
    d = mod.CodexSDKDispatcher()

    def _raise_timeout(*a, **kw):
        raise subprocess.TimeoutExpired(cmd="codex", timeout=1.0)

    monkeypatch.setattr(subprocess, "run", _raise_timeout)

    agent_file = tmp_path / "F3_test.md"
    agent_file.write_text("---\nid: F3\n---\n\nSlow formula.")
    req = DispatchRequest(
        formula_id="architect", agent_file=str(agent_file), prompt="slow", timeout_s=1.0
    )
    result = asyncio.run(d.dispatch(req))
    assert result.status == "timeout"
    assert "timed out" in (result.error or "")


def test_codex_sdk_dispatcher_nonzero_rc(monkeypatch, tmp_path):
    import shutil
    import subprocess

    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/codex" if name == "codex" else None)
    mod = _import_codex_sdk_dispatcher_module()
    d = mod.CodexSDKDispatcher()

    class FakeResult:
        returncode = 1
        stdout = ""
        stderr = "codex: unknown flag --json"

    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: FakeResult())

    agent_file = tmp_path / "F4_test.md"
    agent_file.write_text("---\nid: F4\n---\n\nBad flag formula.")
    req = DispatchRequest(formula_id="documenter", agent_file=str(agent_file), prompt="fail")
    result = asyncio.run(d.dispatch(req))
    assert result.status == "error"
    assert "rc=1" in (result.error or "")
