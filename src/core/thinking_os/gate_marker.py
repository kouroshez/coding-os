"""Panel-scoped `.thinking_os-gate` resolution — dependency-free SSOT.

Kept import-light (os + pathlib only) so both the heavy MCP-server modules and
the bare-`python3` Stop-hook scripts can read the gate the same way. A second
divergent resolver rooted at COS_STATE_DIR left complexity UNKNOWN on every
session (session_enrich audit, root-cause cluster D).
"""

from __future__ import annotations

import os
from pathlib import Path

CYNEFIN_LEVELS = {"CLEAR", "COMPLICATED", "COMPLEX", "CHAOTIC", "CONFUSION", "UNKNOWN"}


def newest_panel_gate() -> Path | None:
    # The gate is panel-scoped: <state>/<agent>/panels/<panel-id>/.thinking_os-gate.
    # The long-lived MCP server has no COS_PANEL_DIR, so reach the panel dir under
    # the agent dir directly and take the freshest gate — the flat state_search_dirs
    # walk stops one level short of the panel subdir.
    agent = os.environ.get("COS_AGENT", "")
    if not agent:
        return None
    panels = Path(os.environ.get("COS_STATE_DIR", ".coding-os")) / agent / "panels"
    if not panels.is_dir():
        return None
    gates = [
        p / ".thinking_os-gate" for p in panels.iterdir() if (p / ".thinking_os-gate").is_file()
    ]
    if not gates:
        return None
    try:
        return max(gates, key=lambda g: g.stat().st_mtime)
    except OSError:
        return gates[0]


def state_search_dirs() -> list[str]:
    # Dirs to search for a per-panel/per-agent state marker, most-specific first:
    # panel dir -> agent dir -> <state>/<agent> -> state dir. The long-lived MCP
    # server has no COS_PANEL_DIR/COS_AGENT_DIR but does know COS_AGENT, so the
    # <state>/<agent> entry is what makes markers resolvable there.
    state_dir = os.environ.get("COS_STATE_DIR", ".coding-os")
    agent = os.environ.get("COS_AGENT", "")
    dirs = [d for d in (os.environ.get("COS_PANEL_DIR"), os.environ.get("COS_AGENT_DIR")) if d]
    if agent:
        dirs.append(str(Path(state_dir) / agent))
    dirs.append(state_dir)
    return dirs


def read_gate_file() -> tuple[str, int]:
    # Format: "<session-or-panel-id> <CLASSIFICATION> <N>"; the id prefix is a
    # session id (ses-…), a panel ppid hash (ppid-…), OR a bare UUID, so skip ANY
    # leading token that is not itself a Cynefin level.
    gate_path = None
    for d in state_search_dirs():
        candidate = Path(d) / ".thinking_os-gate"
        if candidate.exists():
            gate_path = candidate
            break
    if gate_path is None:
        gate_path = newest_panel_gate()
    if gate_path is None:
        return "UNKNOWN", 1
    try:
        parts = gate_path.read_text().strip().split()
        if parts and parts[0].upper() not in CYNEFIN_LEVELS:
            parts = parts[1:]
        complexity = parts[0] if parts else "UNKNOWN"
        dimensions = int(parts[1]) if len(parts) > 1 else 1
        return complexity, dimensions
    except (ValueError, IndexError, OSError):
        return "UNKNOWN", 1
