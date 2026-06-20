"""Smoke test: subsystem module gating end-to-end (TASK-425).

Demonstrates how modules are *handled* — toggling a module puts its MCP tool
family in/out of circuit. Existing tests cover hook overrides
(test_project_overrides) and state/deps (test_cli::TestSubsystems); this pins
the MCP tool gate (`_shared.py::_gated_module` → `module_disabled` envelope)
that nothing else asserts. Mirrors the runtime picture you can see with
`cos module list [--format json]`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from cli.module_commands import module_state_payload  # noqa: E402
from core.thinking_os.tools._shared import _gated_module, fail, ok, safe_tool  # noqa: E402


def _write_disabled(state_dir: Path, disabled: list[str]) -> None:
    """Write a project's subsystems-state.json the way set_module_enabled would."""
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "subsystems-state.json").write_text(
        json.dumps({"version": 1, "disabled": disabled}), encoding="utf-8"
    )


def _envelope(result: object) -> dict:
    """cos_* tools return the envelope as a JSON string — normalise to a dict."""
    return json.loads(result) if isinstance(result, str) else result  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 1. The output shape — what `cos module list` / GET /api/settings/modules return
# ---------------------------------------------------------------------------


def test_module_state_payload_reports_tools_and_hooks_per_module(tmp_path: Path) -> None:
    """No state file = everything enabled; each module reports its hook/tool counts."""
    payload = module_state_payload(tmp_path)
    by_id = {m["id"]: m for m in payload["modules"]}

    assert by_id["kernel"]["kernel"] is True and by_id["kernel"]["enabled"] is True
    assert "docs" in by_id["tasks"]["depends_on"]  # tasks needs docs
    # graph owns the cos_graph_* tool family + its enforce/auto hooks.
    assert by_id["graph"]["tools"] >= 1 and by_id["graph"]["hooks"] >= 1
    # D6-5 (TASK-480): the per-module skills count is part of the contract
    # `cos module list --format json` + the Hub Settings page consume.
    assert by_id["graph"]["skills"] >= 1  # graph owns graph-explorer + graph-os-authoring
    # Untoggled project → all modules report enabled.
    assert all(m["enabled"] for m in payload["modules"])


# ---------------------------------------------------------------------------
# 2. One module off → only its tool family leaves the circuit
# ---------------------------------------------------------------------------


def test_disabled_module_gates_only_its_own_tools(tmp_path: Path, monkeypatch) -> None:
    state = tmp_path / ".coding-os"
    _write_disabled(state, ["graph"])
    monkeypatch.setenv("COS_STATE_DIR", str(state))

    # graph off → cos_graph_* gated to "graph"…
    assert _gated_module("cos_graph_search") == "graph"
    assert _gated_module("cos_graph_impact") == "graph"
    # …while every other family still runs (None = not gated).
    assert _gated_module("cos_task_create") is None
    assert _gated_module("cos_doc_search") is None
    assert _gated_module("cos_search") is None


# ---------------------------------------------------------------------------
# 3. Several off — a "graph-only" project (docs + tasks + memory disabled)
# ---------------------------------------------------------------------------


def test_graph_only_project_gates_the_other_families(tmp_path: Path, monkeypatch) -> None:
    state = tmp_path / ".coding-os"
    # docs+tasks disabled together keeps the tasks→docs dependency valid.
    _write_disabled(state, ["docs", "tasks", "memory"])
    monkeypatch.setenv("COS_STATE_DIR", str(state))

    assert _gated_module("cos_doc_search") == "docs"
    assert _gated_module("cos_task_create") == "tasks"
    assert _gated_module("cos_work_log_append") == "tasks"  # exact (non-prefix) entry
    assert _gated_module("cos_search") == "memory"
    assert _gated_module("cos_learn_extract") == "memory"
    # The one module left on still runs.
    assert _gated_module("cos_graph_query") is None


def test_no_state_file_means_nothing_is_gated(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("COS_STATE_DIR", str(tmp_path / "absent"))
    assert _gated_module("cos_graph_search") is None
    assert _gated_module("cos_task_create") is None


# ---------------------------------------------------------------------------
# 4. The exact envelope the agent receives when it calls a gated tool
# ---------------------------------------------------------------------------


def test_safe_tool_returns_module_disabled_envelope(tmp_path: Path, monkeypatch) -> None:
    state = tmp_path / ".coding-os"
    _write_disabled(state, ["graph"])
    monkeypatch.setenv("COS_STATE_DIR", str(state))

    @safe_tool
    def cos_graph_smoke() -> str:
        return ok({"ran": True})

    env = _envelope(cos_graph_smoke())
    assert env["ok"] is False
    assert env["error"]["category"] == "module_disabled"
    assert "graph" in env["error"]["message"]
    assert "cos module enable graph" in env["error"]["message"]


def test_safe_tool_runs_when_module_enabled(tmp_path: Path, monkeypatch) -> None:
    state = tmp_path / ".coding-os"
    _write_disabled(state, ["memory"])  # graph stays enabled
    monkeypatch.setenv("COS_STATE_DIR", str(state))

    @safe_tool
    def cos_graph_smoke() -> str:
        return ok({"ran": True})

    env = _envelope(cos_graph_smoke())
    assert env["ok"] is True and env["data"]["ran"] is True


# Keep `fail` imported-and-used so the smoke file documents the envelope helpers.
def test_fail_helper_shapes_the_module_disabled_category() -> None:
    env = _envelope(fail("module_disabled", "x", retryable=False))
    assert env["ok"] is False and env["error"]["category"] == "module_disabled"
