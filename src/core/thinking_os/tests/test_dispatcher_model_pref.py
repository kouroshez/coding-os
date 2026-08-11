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
    get_dispatcher,
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


def test_adapter_hint_defaults_none():
    req = DispatchRequest(formula_id="implementer", agent_file="/tmp/x.md", prompt="p")
    assert req.adapter is None


def test_adapter_hint_mismatch_warns_and_proceeds(monkeypatch, caplog):
    monkeypatch.delenv("COS_FORCE_DEFAULT_DISPATCHER", raising=False)
    req = DispatchRequest(
        formula_id="reviewer", agent_file="/tmp/x.md", prompt="p", adapter="codex"
    )
    with caplog.at_level("WARNING", logger="coding_os.dispatcher"):
        dispatcher = get_dispatcher(agent="claude", request=req)

    assert dispatcher is not None
    record = next(r for r in caplog.records if "adapter hint" in r.getMessage())
    assert "'codex'" in record.getMessage()
    assert "'claude'" in record.getMessage()


def test_matching_adapter_hint_stays_silent(monkeypatch, caplog):
    monkeypatch.delenv("COS_FORCE_DEFAULT_DISPATCHER", raising=False)
    req = DispatchRequest(
        formula_id="reviewer", agent_file="/tmp/x.md", prompt="p", adapter="codex"
    )
    with caplog.at_level("WARNING", logger="coding_os.dispatcher"):
        get_dispatcher(agent="codex", request=req)

    assert not [r for r in caplog.records if "adapter hint" in r.getMessage()]


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


def _codex_dispatch_argv(monkeypatch, tmp_path, model):
    import shutil
    import subprocess

    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/codex" if name == "codex" else None)
    mod = _import_codex_sdk_dispatcher_module()
    dispatcher = mod.CodexSDKDispatcher()

    captured: dict = {}

    class FakeResult:
        returncode = 0
        stdout = _codex_jsonl({"answer": 1})
        stderr = ""

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["input"] = kwargs["input"]
        return FakeResult()

    monkeypatch.setattr(subprocess, "run", fake_run)

    agent_file = tmp_path / "F_model.md"
    agent_file.write_text("---\nid: F\n---\n\nModel forward formula.")
    req = DispatchRequest(
        formula_id="documenter", agent_file=str(agent_file), prompt="go", model=model
    )
    asyncio.run(dispatcher.dispatch(req))
    return captured


def test_codex_forwards_model_flag(monkeypatch, tmp_path):
    captured = _codex_dispatch_argv(monkeypatch, tmp_path, model="gpt-5-codex")
    cmd = captured["cmd"]
    flag_at = cmd.index("--model")
    assert cmd[flag_at + 1] == "gpt-5-codex"
    assert cmd[-1] == "-"
    assert "Model forward formula" in captured["input"]


def test_codex_omits_model_flag_when_unset(monkeypatch, tmp_path):
    captured = _codex_dispatch_argv(monkeypatch, tmp_path, model=None)
    assert "--model" not in captured["cmd"]
