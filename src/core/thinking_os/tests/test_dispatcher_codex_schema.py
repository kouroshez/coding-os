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

import pytest

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


def test_codex_sdk_dispatcher_surfaces_jsonl_failure(monkeypatch, tmp_path):
    import json
    import shutil
    import subprocess

    monkeypatch.setattr(shutil, "which", lambda _: "/usr/bin/codex")
    mod = _import_codex_sdk_dispatcher_module()

    class FakeResult:
        returncode = 1
        stdout = json.dumps(
            {"type": "turn.failed", "error": {"message": "provider usage exhausted"}}
        )
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: FakeResult())
    agent_file = tmp_path / "F_provider_error.md"
    agent_file.write_text("---\nid: F\n---\n\nReturn JSON.")
    result = asyncio.run(
        mod.CodexSDKDispatcher().dispatch(
            DispatchRequest(formula_id="reviewer", agent_file=str(agent_file), prompt="review")
        )
    )
    assert result.status == "error"
    assert result.error == "provider usage exhausted"


def test_codex_sdk_dispatcher_rejects_missing_json(monkeypatch, tmp_path):
    import json
    import shutil
    import subprocess

    monkeypatch.setattr(shutil, "which", lambda _: "/usr/bin/codex")
    mod = _import_codex_sdk_dispatcher_module()
    dispatcher = mod.CodexSDKDispatcher()

    class FakeResult:
        returncode = 0
        stdout = json.dumps(
            {
                "type": "item.completed",
                "item": {"type": "agent_message", "text": "no structured result"},
            }
        )
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: FakeResult())
    agent_file = tmp_path / "F_missing_json.md"
    agent_file.write_text("---\nid: F\n---\n\nReturn JSON.")
    result = asyncio.run(
        dispatcher.dispatch(
            DispatchRequest(formula_id="reviewer", agent_file=str(agent_file), prompt="review")
        )
    )
    assert result.status == "error"
    assert "no usable EvidenceBundle JSON" in (result.error or "")


def test_codex_sdk_dispatcher_rejects_unenforceable_budget(monkeypatch, tmp_path):
    import shutil
    import subprocess

    monkeypatch.setattr(shutil, "which", lambda _: "/usr/bin/codex")
    called = False

    def fake_run(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(subprocess, "run", fake_run)
    mod = _import_codex_sdk_dispatcher_module()
    agent_file = tmp_path / "F_budget.md"
    agent_file.write_text("---\nid: F\n---\n\nReturn JSON.")
    result = asyncio.run(
        mod.CodexSDKDispatcher().dispatch(
            DispatchRequest(
                formula_id="reviewer",
                agent_file=str(agent_file),
                prompt="review",
                max_budget_usd=0.25,
            )
        )
    )
    assert result.status == "error"
    assert "cannot enforce" in (result.error or "")
    assert called is False


def test_codex_sdk_dispatcher_forwards_output_schema(monkeypatch, tmp_path):
    import json
    import shutil
    import subprocess

    monkeypatch.setattr(shutil, "which", lambda _: "/usr/bin/codex")
    captured: dict = {}

    class FakeResult:
        returncode = 0
        stdout = _codex_jsonl({"summary": "done"})
        stderr = ""

    def fake_run(cmd, **kwargs):
        schema_path = Path(cmd[cmd.index("--output-schema") + 1])
        captured["schema"] = json.loads(schema_path.read_text())
        return FakeResult()

    monkeypatch.setattr(subprocess, "run", fake_run)
    mod = _import_codex_sdk_dispatcher_module()
    monkeypatch.setattr(
        mod,
        "_resolve_output_schema",
        lambda _: {
            "type": "object",
            "properties": {"summary": {"type": "string"}},
            "required": ["summary"],
            "additionalProperties": False,
        },
    )
    agent_file = tmp_path / "F_schema.md"
    agent_file.write_text(
        "---\nid: F\nstructured_output: true\n"
        "output_schema: cognition.ReviewerOutput\n---\n\nReturn JSON."
    )
    result = asyncio.run(
        mod.CodexSDKDispatcher().dispatch(
            DispatchRequest(formula_id="reviewer", agent_file=str(agent_file), prompt="review")
        )
    )
    assert result.status == "ok"
    assert captured["schema"]["type"] == "object"


def test_codex_strict_schema_normalizes_nested_objects():
    mod = _import_codex_sdk_dispatcher_module()
    schema = {
        "type": "object",
        "properties": {
            "result": {
                "type": "object",
                "properties": {"summary": {"type": "string"}},
                "required": ["summary"],
            }
        },
        "required": ["result"],
    }

    assert mod._normalize_strict_schema(schema) is True
    assert schema["additionalProperties"] is False
    assert schema["properties"]["result"]["additionalProperties"] is False


@pytest.mark.parametrize(
    "schema",
    [
        {"type": "object", "additionalProperties": True},
        {
            "type": "object",
            "properties": {"required_value": {}, "defaulted_value": {}},
            "required": ["required_value"],
        },
    ],
)
def test_codex_strict_schema_rejects_incompatible_objects(schema):
    mod = _import_codex_sdk_dispatcher_module()
    assert mod._normalize_strict_schema(schema) is False


def test_codex_python_sdk_backend(monkeypatch, tmp_path):
    import shutil
    import sys
    import types

    monkeypatch.setenv("COS_CODEX_DISPATCH_BACKEND", "python-sdk")
    monkeypatch.setattr(shutil, "which", lambda _: None)
    captured: dict = {}
    fake_module = types.ModuleType("openai_codex")

    class FakeConfig:
        def __init__(self, **kwargs):
            captured["config"] = kwargs

    class FakeCodex:
        def __init__(self, config):
            captured["client_config"] = config

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def thread_start(self, **kwargs):
            captured["thread"] = kwargs
            return FakeThread()

    class FakeThread:
        async def run(self, prompt, **kwargs):
            captured["prompt"] = prompt
            captured["run"] = kwargs
            return types.SimpleNamespace(
                status="completed",
                error=None,
                items=[],
                usage=None,
                final_response='```json\n{"summary": "sdk"}\n```',
            )

    fake_module.ApprovalMode = types.SimpleNamespace(deny_all="deny_all")
    fake_module.Sandbox = types.SimpleNamespace(read_only="read_only")
    fake_module.AsyncCodex = FakeCodex
    fake_module.CodexConfig = FakeConfig
    monkeypatch.setitem(sys.modules, "openai_codex", fake_module)

    mod = _import_codex_sdk_dispatcher_module()
    agent_file = tmp_path / "F_sdk.md"
    agent_file.write_text("---\nid: F\n---\n\nReturn JSON.")
    result = asyncio.run(
        mod.CodexSDKDispatcher().dispatch(
            DispatchRequest(formula_id="reviewer", agent_file=str(agent_file), prompt="review")
        )
    )
    assert result.status == "ok"
    assert result.output_json == {"summary": "sdk"}
    assert "codex_bin" not in captured["config"]
    assert captured["config"]["config_overrides"] == (
        "features.hooks=false",
        "mcp_servers={}",
    )
    assert captured["thread"]["approval_mode"] == "deny_all"
    assert captured["thread"]["sandbox"] == "read_only"
