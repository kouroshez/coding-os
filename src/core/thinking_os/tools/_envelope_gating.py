"""MCP envelope — which tools a disabled subsystem module owns.

Two enforcement points share one answer. `_gated_module` is the per-call gate
`safe_tool` consults so a tool from a disabled module fails loudly with
`module_disabled` instead of behaving as if it had vanished;
`apply_module_tool_gating` is the startup sweep that removes those same tools
from the served surface, so an agent never sees a tool it cannot call.

Sources: `src/core/subsystems.yaml` (a tool entry ending in `*` matches a
prefix family) plus `$COS_STATE_DIR/subsystems-state.json`. Both reads are
fail-open — an unreadable manifest or state file means no gating and a full
surface, never a half-served one.

`_MODULE_GATE_CACHE` is module-level state that must be reached through this
module (or the `_shared` re-export, which binds the same dict object): tests
reset it in place between cases.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger("coding_os.tools._shared")

_MODULE_GATE_CACHE: dict[str, list[tuple[str, str]] | None] = {"map": None}


def _tool_module_map() -> list[tuple[str, str]]:
    cached = _MODULE_GATE_CACHE["map"]
    if cached is not None:
        return cached
    pairs: list[tuple[str, str]] = []
    try:
        from pathlib import Path

        import yaml

        manifest = Path(__file__).resolve().parents[2] / "subsystems.yaml"
        data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
        for module in data.get("modules") or []:
            if module.get("kernel"):
                continue
            for tool in module.get("tools") or []:
                pairs.append((str(tool), str(module["id"])))
    except Exception as exc:
        logger.debug("module gate map unavailable: %s", exc)
    _MODULE_GATE_CACHE["map"] = pairs
    return pairs


def _disabled_modules() -> set[str]:
    try:
        from pathlib import Path

        from thinking_os.database import get_active_project_root, resolve_db_path

        # A bound Hub request scope must win over the ambient $COS_STATE_DIR
        # (the launch project's), else every /api/p/<slug>/* call is gated by
        # the launch project's enabled-modules set instead of the slug's.
        if get_active_project_root() is not None:
            state_dir = resolve_db_path().parent
        else:
            state_dir = Path(os.environ.get("COS_STATE_DIR") or ".coding-os")
        state_file = state_dir / "subsystems-state.json"
        if not state_file.is_file():
            return set()
        data = json.loads(state_file.read_text(encoding="utf-8"))
        return {str(x) for x in data.get("disabled") or []}
    except Exception as exc:
        logger.debug("subsystems state unreadable (%s) — gating off", exc)
        return set()


def _gated_module(tool_name: str) -> str | None:
    disabled = _disabled_modules()
    if not disabled:
        return None
    for pattern, module_id in _tool_module_map():
        if module_id not in disabled:
            continue
        if pattern.endswith("*"):
            if tool_name.startswith(pattern[:-1]):
                return module_id
        elif tool_name == pattern:
            return module_id
    return None


# Startup-time surface removal (TASK-476): a disabled module's tools must
# VANISH from the served list_tools, not merely fail when called — else the
# agent still sees them and hallucinates calls to a dead tool. The per-call
# safe_tool gate stays as defense-in-depth (a client holding a cached
# tool list, or a module toggled mid-session). Fail-open: any error leaves the
# full surface intact rather than serving a half-surface.
def apply_module_tool_gating(mcp: Any) -> dict[str, Any]:
    """Remove disabled-module-owned tools from the live MCP tool surface."""
    disabled = _disabled_modules()
    if not disabled:
        return {"removed": [], "disabled_modules": []}
    removed: list[str] = []
    try:
        for name in [tool.name for tool in mcp._tool_manager.list_tools()]:
            if _gated_module(name):
                mcp.remove_tool(name)
                removed.append(name)
    except Exception as exc:
        logger.debug("module tool-surface gating skipped (%s) — full surface served", exc)
    return {"removed": sorted(removed), "disabled_modules": sorted(disabled)}
