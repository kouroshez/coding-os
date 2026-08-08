"""Live-registry guard: the subsystems module gate fires on the REGISTERED MCP
tool name, not the Python function name.

Regression for the F1 bug (audit-2026-06): cos_search / cos_timeline /
cos_details are registered from functions named thinking_os_* — the @safe_tool
gate keyed on fn.__name__, so disabling the memory module never gated them
(the tool ran anyway, contradicting the disable contract). The fix passes
`name=` to @safe_tool. This test calls the tools through the live FastMCP
registry with their module disabled and asserts the module_disabled envelope,
so any future function-name/registration drift fails CI instead of silently
re-opening the gate.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
import server

from core.thinking_os.tools._shared import _gated_module, _tool_module_map

# Registered cos_* tools that intentionally belong to NO module — always served
# on every profile. Kept a small, explicit, reviewed list: adding a tool here is
# a deliberate "this is kernel" decision, not an accident. classify=Record Gate
# (core loop) · health=diagnostic · traceability/failure_pattern=ambiguous
# ownership, deliberately not force-mapped.
_KERNEL_TOOLS = {
    "cos_classify_prompt",
    "cos_health",
    "cos_traceability",
    "cos_failure_pattern_query",
}


def _matches_a_module(tool_name: str) -> bool:
    for pattern, _module_id in _tool_module_map():
        if pattern.endswith("*"):
            if tool_name.startswith(pattern[:-1]):
                return True
        elif tool_name == pattern:
            return True
    return False


def _disable(tmp_path: Path, modules: list[str]) -> Path:
    state = tmp_path / ".coding-os"
    state.mkdir(parents=True, exist_ok=True)
    (state / "subsystems-state.json").write_text(
        json.dumps({"version": 1, "disabled": modules}), encoding="utf-8"
    )
    return state


def _call(name: str, args: dict) -> str:
    # The gate short-circuits before the tool body, so a disabled-module call
    # needs no DB; stringify covers any FastMCP call_tool return shape.
    return str(asyncio.run(server.mcp.call_tool(name, args)))


# The three tools whose function name (thinking_os_*) differs from the
# registered MCP name (cos_*) — the exact F1 blind spot.
_MEMORY_NAME_MISMATCH = [
    ("cos_search", {"query": "x"}),
    ("cos_timeline", {}),
    ("cos_details", {"pattern_id": 1}),
]


@pytest.mark.parametrize("tool, args", _MEMORY_NAME_MISMATCH)
def test_memory_tool_gates_on_registered_name(tool, args, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("COS_STATE_DIR", str(_disable(tmp_path, ["memory"])))
    out = _call(tool, args)
    assert "module_disabled" in out, f"{tool} did not gate when memory disabled: {out[:200]}"


def test_gate_is_module_specific(tmp_path, monkeypatch) -> None:
    """Disabling memory gates memory tools by their registered name, not others."""
    monkeypatch.setenv("COS_STATE_DIR", str(_disable(tmp_path, ["memory"])))
    assert _gated_module("cos_search") == "memory"
    assert _gated_module("cos_timeline") == "memory"
    assert _gated_module("cos_details") == "memory"
    assert _gated_module("cos_graph_query") is None  # graph still enabled


def test_every_subsystems_tool_name_is_registered(tmp_path) -> None:
    """Each concrete (non-prefix) tool in subsystems.yaml resolves to a live MCP
    tool, and each prefix family has at least one registered member — so the
    gate map can never reference a name the server does not actually expose."""
    import yaml

    repo_root = Path(server.__file__).resolve().parents[3]
    sub = yaml.safe_load((repo_root / "src/core/subsystems.yaml").read_text(encoding="utf-8"))
    registered = {t.name for t in asyncio.run(server.mcp.list_tools())}

    for module in sub["modules"]:
        if module.get("kernel"):
            continue
        for tool in module.get("tools") or []:
            if tool.endswith("*"):
                prefix = tool[:-1]
                assert any(n.startswith(prefix) for n in registered), (
                    f"subsystems.yaml module '{module['id']}' lists prefix '{tool}' "
                    f"but no registered MCP tool matches it"
                )
            else:
                assert tool in registered, (
                    f"subsystems.yaml module '{module['id']}' lists '{tool}' "
                    f"but it is not a registered MCP tool name"
                )


def test_every_registered_tool_has_a_module_owner_or_is_kernel() -> None:
    """Reverse totality — the tool-side twin of the hook-owner invariant.

    Every registered cos_* tool must either match a subsystems.yaml module tool
    family or be an explicit kernel tool. A tool added without a module owner
    then fails here instead of silently surviving on a disabled-module surface."""
    registered = {t.name for t in asyncio.run(server.mcp.list_tools())}
    cos_tools = {n for n in registered if n.startswith("cos_")}
    orphans = sorted(n for n in cos_tools if n not in _KERNEL_TOOLS and not _matches_a_module(n))
    assert not orphans, (
        f"registered cos_* tools with no module owner and not kernel: {orphans} — "
        f"add each to its module's tools[] in subsystems.yaml, or (if intentionally "
        f"always-on) to _KERNEL_TOOLS with a one-line rationale"
    )
