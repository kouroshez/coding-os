"""TASK-354 — safe_tool module gating: disabled subsystems fail loud, not silent."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools._shared import _MODULE_GATE_CACHE, safe_tool  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_gate_cache():
    _MODULE_GATE_CACHE["map"] = None
    yield
    _MODULE_GATE_CACHE["map"] = None


def _disable(tmp_path: Path, *modules: str) -> None:
    state = tmp_path / "subsystems-state.json"
    state.write_text(json.dumps({"version": 1, "disabled": list(modules)}), encoding="utf-8")


@safe_tool
def cos_task_dummy() -> str:
    return json.dumps({"ok": True, "data": {"ran": True}})


@safe_tool
def cos_graph_dummy() -> str:
    return json.dumps({"ok": True, "data": {"ran": True}})


@safe_tool
def cos_health_dummy() -> str:
    return json.dumps({"ok": True, "data": {"ran": True}})


def test_disabled_module_gates_prefix_family(tmp_path, monkeypatch):
    monkeypatch.setenv("COS_STATE_DIR", str(tmp_path))
    _disable(tmp_path, "tasks")
    payload = json.loads(cos_task_dummy())
    assert payload["ok"] is False
    assert payload["error"]["category"] == "module_disabled"
    assert payload["error"]["retryable"] is False
    assert "tasks" in payload["error"]["message"]
    assert "cos module enable tasks" in payload["error"]["message"]


def test_other_families_unaffected_by_unrelated_disable(tmp_path, monkeypatch):
    monkeypatch.setenv("COS_STATE_DIR", str(tmp_path))
    _disable(tmp_path, "tasks")
    assert json.loads(cos_graph_dummy())["ok"] is True
    assert json.loads(cos_health_dummy())["ok"] is True


def test_no_state_file_means_no_gating(tmp_path, monkeypatch):
    monkeypatch.setenv("COS_STATE_DIR", str(tmp_path))
    assert json.loads(cos_task_dummy())["ok"] is True


def test_corrupt_state_fails_open(tmp_path, monkeypatch):
    monkeypatch.setenv("COS_STATE_DIR", str(tmp_path))
    (tmp_path / "subsystems-state.json").write_text("{not json", encoding="utf-8")
    assert json.loads(cos_task_dummy())["ok"] is True


def test_reenable_lifts_the_gate(tmp_path, monkeypatch):
    monkeypatch.setenv("COS_STATE_DIR", str(tmp_path))
    _disable(tmp_path, "graph")
    assert json.loads(cos_graph_dummy())["ok"] is False
    _disable(tmp_path)  # empty disabled list
    assert json.loads(cos_graph_dummy())["ok"] is True
