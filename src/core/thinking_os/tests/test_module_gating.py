"""TASK-354 — safe_tool module gating: disabled subsystems fail loud, not silent."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools._shared import (
    _MODULE_GATE_CACHE,
    _gated_module,
    apply_module_tool_gating,
    safe_tool,
)


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


# ---------------------------------------------------------------------------
# TASK-476 — startup surface removal: a disabled module's tools VANISH from
# list_tools (not merely fail at call), so the agent never sees/hallucinates
# them. Complements the per-call gate above (defense-in-depth) which the
# tests above cover.
# ---------------------------------------------------------------------------


def _build_mcp(*names: str):
    from mcp.server.fastmcp import FastMCP

    def _stub() -> str:
        return "x"

    mcp = FastMCP("surface-removal-test")
    for tool_name in names:
        mcp.tool(name=tool_name)(_stub)
    return mcp


def _live_names(mcp) -> set[str]:
    return {tool.name for tool in mcp._tool_manager.list_tools()}


def test_surface_removal_drops_disabled_family_keeps_rest(tmp_path, monkeypatch):
    monkeypatch.setenv("COS_STATE_DIR", str(tmp_path))
    _disable(tmp_path, "graph")
    mcp = _build_mcp("cos_graph_query", "cos_graph_context", "cos_task_show", "cos_health")
    summary = apply_module_tool_gating(mcp)
    assert _live_names(mcp) == {"cos_task_show", "cos_health"}  # graph family gone
    assert set(summary["removed"]) == {"cos_graph_query", "cos_graph_context"}
    assert summary["disabled_modules"] == ["graph"]


def test_surface_removal_is_noop_when_nothing_disabled(tmp_path, monkeypatch):
    # Acceptance #2 — default all-on consumer: surface is byte-identical.
    monkeypatch.setenv("COS_STATE_DIR", str(tmp_path))
    mcp = _build_mcp("cos_graph_query", "cos_task_show", "cos_health")
    before = _live_names(mcp)
    summary = apply_module_tool_gating(mcp)
    assert _live_names(mcp) == before
    assert summary == {"removed": [], "disabled_modules": []}


def test_surface_removal_corrupt_state_serves_full_surface(tmp_path, monkeypatch):
    # Acceptance #3 — corrupt state => fail-open, never a half-surface.
    monkeypatch.setenv("COS_STATE_DIR", str(tmp_path))
    (tmp_path / "subsystems-state.json").write_text("{not json", encoding="utf-8")
    mcp = _build_mcp("cos_graph_query", "cos_task_show")
    summary = apply_module_tool_gating(mcp)
    assert _live_names(mcp) == {"cos_graph_query", "cos_task_show"}
    assert summary["removed"] == []


def test_surface_removal_fails_open_on_manager_error(tmp_path, monkeypatch):
    # A list_tools/remove error must be swallowed (fail-open), never propagate.
    monkeypatch.setenv("COS_STATE_DIR", str(tmp_path))
    _disable(tmp_path, "graph")
    mcp = _build_mcp("cos_graph_query")
    monkeypatch.setattr(
        mcp._tool_manager,
        "list_tools",
        lambda: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    summary = apply_module_tool_gating(mcp)  # must not raise
    assert summary["removed"] == []
    assert summary["disabled_modules"] == ["graph"]


# ---------------------------------------------------------------------------
# TASK-477 — the cognition/observability modules were `tools: []` (toggleable
# but shed nothing). They now own their reasoning/metrics surface; classify +
# health stay kernel by design. Reads the real subsystems.yaml via _gated_module.
# ---------------------------------------------------------------------------


def test_cognition_disable_gates_reasoning_keeps_kernel(tmp_path, monkeypatch):
    monkeypatch.setenv("COS_STATE_DIR", str(tmp_path))
    _disable(tmp_path, "cognition")
    assert _gated_module("cos_compose_chain") == "cognition"
    assert _gated_module("cos_dispatch_formula_run") == "cognition"
    assert _gated_module("cos_route_model") == "cognition"
    assert _gated_module("cos_supervise_record_output") == "cognition"
    # Record Gate + diagnostic stay kernel — never gated by a module toggle.
    assert _gated_module("cos_classify_prompt") is None
    assert _gated_module("cos_health") is None


def test_observability_disable_gates_metrics_and_trajectory(tmp_path, monkeypatch):
    monkeypatch.setenv("COS_STATE_DIR", str(tmp_path))
    _disable(tmp_path, "observability")
    assert _gated_module("cos_metric_record") == "observability"
    assert _gated_module("cos_log_query") == "observability"
    assert _gated_module("cos_trajectory_snapshot") == "observability"
    assert _gated_module("cos_presence_query") == "observability"


def test_memory_disable_gates_retrieval_promote_digest(tmp_path, monkeypatch):
    monkeypatch.setenv("COS_STATE_DIR", str(tmp_path))
    _disable(tmp_path, "memory")
    assert _gated_module("cos_retrieval_cite") == "memory"
    assert _gated_module("cos_promote") == "memory"
    assert _gated_module("cos_digest_regenerate") == "memory"
