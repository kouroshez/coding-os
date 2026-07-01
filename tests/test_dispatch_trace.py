"""TASK-667 — dispatcher run-event tee to the append-only cognition trace sink."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_dispatcher_module():
    spec = importlib.util.spec_from_file_location(
        "coding_os_sdk_dispatcher_trace_under_test",
        _REPO_ROOT / "src" / "adapters" / "claude" / "sdk_dispatcher.py",
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    tos = _REPO_ROOT / "src" / "core" / "thinking_os"
    if str(tos) not in sys.path:
        sys.path.insert(0, str(tos))
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def dispatcher_mod():
    return _load_dispatcher_module()


def _read_trace(agent_dir: Path, session_id: str) -> list[dict]:
    path = agent_dir / "traces" / f"{session_id}.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def test_emit_appends_dispatch_event(dispatcher_mod, tmp_path, monkeypatch):
    monkeypatch.setenv("COS_AGENT_DIR", str(tmp_path))
    dispatcher_mod._emit_dispatch_trace(
        "ses-dt-1", "dispatch_started", "implementer", {"formula_id": "impl"}
    )
    events = _read_trace(tmp_path, "ses-dt-1")
    assert len(events) == 1
    assert events[0]["kind"] == "dispatch_started"
    assert events[0]["role"] == "implementer"
    assert events[0]["data"]["formula_id"] == "impl"


def test_content_off_by_default(dispatcher_mod, monkeypatch):
    monkeypatch.delenv("COS_DISPATCH_EVENT_CONTENT", raising=False)
    assert dispatcher_mod._dispatch_trace_content_enabled() is False


def test_content_flag_on(dispatcher_mod, monkeypatch):
    monkeypatch.setenv("COS_DISPATCH_EVENT_CONTENT", "1")
    assert dispatcher_mod._dispatch_trace_content_enabled() is True


def test_emit_is_failopen(dispatcher_mod, monkeypatch):
    def _boom(*args, **kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr("thinking_os.tracing.emit", _boom)
    # Must swallow and return None — never raise into the dispatch path.
    assert (
        dispatcher_mod._emit_dispatch_trace("ses-x", "dispatch_turn", "impl", {"seq": 1})
        is None
    )
