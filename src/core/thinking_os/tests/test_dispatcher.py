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
from pathlib import Path

import pytest

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


# ---------------------------------------------------------------------------
# DefaultDispatcher behaviour
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Factory detection
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# ClaudeSDKDispatcher — availability + mocked dispatch
# ---------------------------------------------------------------------------


def _import_claude_sdk_dispatcher_module():
    """Load adapters/claude/sdk_dispatcher.py by path (same way factory does)."""
    import importlib.util

    adapter_path = _CORE_TOS.parent.parent / "adapters" / "claude" / "sdk_dispatcher.py"
    spec = importlib.util.spec_from_file_location(
        "_test_claude_sdk_dispatcher",
        adapter_path,
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
    agent_file.write_text("---\nid: F99\nname: test\n---\n\nTest formula body.")

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
    assert "no usable JSON" in (result.error or "")


# ---------------------------------------------------------------------------
# CodexSDKDispatcher — availability + mocked dispatch
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


def test_codex_sdk_dispatcher_name():
    mod = _import_codex_sdk_dispatcher_module()
    d = mod.CodexSDKDispatcher()
    assert d.name == "codex-sdk"


def test_codex_sdk_dispatcher_unavailable_when_no_binary(monkeypatch):
    import shutil

    monkeypatch.setattr(shutil, "which", lambda _: None)
    mod = _import_codex_sdk_dispatcher_module()
    d = mod.CodexSDKDispatcher()
    assert d.available() is False


def test_codex_sdk_dispatcher_available_when_binary_present(monkeypatch):
    import shutil

    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/codex" if name == "codex" else None)
    mod = _import_codex_sdk_dispatcher_module()
    d = mod.CodexSDKDispatcher()
    assert d.available() is True


def test_codex_sdk_dispatcher_error_when_unavailable(monkeypatch, tmp_path):
    """dispatch() returns error result when binary absent."""
    import shutil

    monkeypatch.setattr(shutil, "which", lambda _: None)
    mod = _import_codex_sdk_dispatcher_module()
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
    """Mock subprocess.run to simulate a successful codex run."""
    import shutil
    import subprocess

    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/codex" if name == "codex" else None)
    mod = _import_codex_sdk_dispatcher_module()
    d = mod.CodexSDKDispatcher()

    fake_output = '```json\n{"summary": "done", "risks": []}\n```'

    class FakeResult:
        returncode = 0
        stdout = fake_output
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: FakeResult())

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
    """Non-zero return code → error result."""
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


# ---------------------------------------------------------------------------
# Model resolution at request build (claude-sdk.md §7.3 — model_pref × gate)
# ---------------------------------------------------------------------------


def _build_request(monkeypatch, tmp_path, **kwargs):
    import sys

    if str(_CORE_TOS) not in sys.path:
        sys.path.insert(0, str(_CORE_TOS))
    monkeypatch.setenv("COS_AGENT_DIR", str(tmp_path))
    from tools.cognition import _build_dispatch_request

    return _build_dispatch_request(
        kwargs.pop("formula_id", "reviewer"),
        "test-session-model-res",
        "TASK-TEST",
        "developer",
        "standard",
        None,
        **kwargs,
    )


def test_model_pref_resolves_from_complexity(monkeypatch, tmp_path):
    # reviewer.md frontmatter declares model_pref {complicated: sonnet, complex: opus}.
    req = _build_request(monkeypatch, tmp_path, complexity="COMPLEX")
    assert req.model == "opus"

    req = _build_request(monkeypatch, tmp_path, complexity="complicated")
    assert req.model == "sonnet"


def test_explicit_model_overrides_model_pref(monkeypatch, tmp_path):
    req = _build_request(monkeypatch, tmp_path, model="haiku", complexity="COMPLEX")
    assert req.model == "haiku"


def test_no_complexity_and_no_pref_leaves_sdk_default(monkeypatch, tmp_path):
    req = _build_request(monkeypatch, tmp_path)
    assert req.model is None

    req = _build_request(monkeypatch, tmp_path, complexity="CLEAR")
    assert req.model is None


# ---------------------------------------------------------------------------
# Adapter hint carrier (dispatcher-contract.md rule 6)
# ---------------------------------------------------------------------------


def test_new_adapter_fields_default_none():
    req = DispatchRequest(formula_id="implementer", agent_file="/tmp/x.md", prompt="p")
    assert req.adapter is None
    assert req.adapter_budget_usd is None


def test_adapter_hint_mismatch_warns_and_proceeds(monkeypatch, caplog):
    monkeypatch.delenv("COS_FORCE_DEFAULT_DISPATCHER", raising=False)
    req = DispatchRequest(
        formula_id="reviewer", agent_file="/tmp/x.md", prompt="p", adapter="codex"
    )
    with caplog.at_level("WARNING", logger="coding_os.dispatcher"):
        dispatcher = get_dispatcher(agent="cursor", request=req)

    assert dispatcher is not None
    record = next(r for r in caplog.records if "adapter hint" in r.getMessage())
    assert "'codex'" in record.getMessage()
    assert "'cursor'" in record.getMessage()


def test_matching_adapter_hint_stays_silent(monkeypatch, caplog):
    monkeypatch.delenv("COS_FORCE_DEFAULT_DISPATCHER", raising=False)
    req = DispatchRequest(
        formula_id="reviewer", agent_file="/tmp/x.md", prompt="p", adapter="cursor"
    )
    with caplog.at_level("WARNING", logger="coding_os.dispatcher"):
        get_dispatcher(agent="cursor", request=req)

    assert not [r for r in caplog.records if "adapter hint" in r.getMessage()]


# ---------------------------------------------------------------------------
# Preset hints + empirical fallback (claude-sdk.md §7.3 tiers 2 and 4)
# ---------------------------------------------------------------------------


def _resolution_env(monkeypatch, tmp_path):
    import sys

    if str(_CORE_TOS) not in sys.path:
        sys.path.insert(0, str(_CORE_TOS))
    monkeypatch.setenv("COS_AGENT_DIR", str(tmp_path))
    from database import init_db

    db_path = str(tmp_path / "test.db")
    conn = init_db(db_path)
    conn.close()
    return db_path


def test_preset_hint_beats_role_pref(monkeypatch, tmp_path):
    db_path = _resolution_env(monkeypatch, tmp_path)
    import sqlite3

    import formula_composer
    from tools.cognition import _build_dispatch_request

    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO persona_selections "
        "(session_id, task_marker, persona_id, confidence, reason, intensity) "
        "VALUES ('ses-hint', 'test-preset', 'reviewer', 1.0, 'preset', 'default')"
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(
        formula_composer,
        "load_presets",
        lambda: (
            [
                {
                    "id": "test-preset",
                    "chain": ["reviewer"],
                    "roles_adapter_hints": {"reviewer": {"model_pref": {"complex": "haiku"}}},
                }
            ],
            "v-test",
        ),
    )

    # reviewer.md role_pref says complex→opus; the preset hint must win.
    req = _build_dispatch_request(
        "reviewer", "ses-hint", "TASK-T", "dev", "standard", None, "", "COMPLEX", db_path
    )
    assert req.model == "haiku"


def test_empirical_fallback_used_when_history_exists(monkeypatch, tmp_path):
    db_path = _resolution_env(monkeypatch, tmp_path)
    from tools import routing
    from tools.cognition import _build_dispatch_request

    monkeypatch.setattr(
        routing,
        "route_model",
        lambda conn, **kw: {"recommended_model": "empirical-model", "data_points": 12},
    )

    # documenter has no model_pref in frontmatter and no preset row exists →
    # tier 4 empirical must fire.
    req = _build_dispatch_request(
        "documenter", "ses-emp", "TASK-T", "dev", "standard", None, "", "COMPLEX", db_path
    )
    assert req.model == "empirical-model"


def test_cold_start_empirical_is_ignored(monkeypatch, tmp_path):
    db_path = _resolution_env(monkeypatch, tmp_path)
    from tools import routing
    from tools.cognition import _build_dispatch_request

    monkeypatch.setattr(
        routing,
        "route_model",
        lambda conn, **kw: {"recommended_model": "static-default", "data_points": 0},
    )

    req = _build_dispatch_request(
        "documenter", "ses-cold", "TASK-T", "dev", "standard", None, "", "COMPLEX", db_path
    )
    assert req.model is None


# ---------------------------------------------------------------------------
# Codex dispatcher forwards request.model (dispatcher-contract parity)
# ---------------------------------------------------------------------------


def _codex_dispatch_argv(monkeypatch, tmp_path, model):
    import shutil
    import subprocess

    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/codex" if name == "codex" else None)
    mod = _import_codex_sdk_dispatcher_module()
    dispatcher = mod.CodexSDKDispatcher()

    captured: dict = {}

    class FakeResult:
        returncode = 0
        stdout = '{"answer": 1}'
        stderr = ""

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return FakeResult()

    monkeypatch.setattr(subprocess, "run", fake_run)

    agent_file = tmp_path / "F_model.md"
    agent_file.write_text("---\nid: F\n---\n\nModel forward formula.")
    req = DispatchRequest(
        formula_id="documenter", agent_file=str(agent_file), prompt="go", model=model
    )
    asyncio.run(dispatcher.dispatch(req))
    return captured["cmd"]


def test_codex_forwards_model_flag(monkeypatch, tmp_path):
    cmd = _codex_dispatch_argv(monkeypatch, tmp_path, model="gpt-5-codex")
    flag_at = cmd.index("--model")
    assert cmd[flag_at + 1] == "gpt-5-codex"
    assert cmd[-1].startswith("---") or len(cmd[-1]) > 20  # prompt stays last


def test_codex_omits_model_flag_when_unset(monkeypatch, tmp_path):
    cmd = _codex_dispatch_argv(monkeypatch, tmp_path, model=None)
    assert "--model" not in cmd
