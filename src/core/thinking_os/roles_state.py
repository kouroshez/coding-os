"""Thinking OS — role-chain state-file writer (single source of truth).

Both the MCP tool ``cos_compose_chain`` (tools/cognition.py) and the
auto-compose hook helper (hooks/_helpers/auto_compose.py) need to persist
the composed chain to the agent-scoped state files the Hub
``/api/roles/chain`` endpoint reads:

    <agent_dir>/.roles   — JSON list of role ids (the chain)
    <agent_dir>/.role    — lead role id (chain[0])

Keeping the writer in one place stops the two call sites from drifting
(the inline version in cognition.py was the only writer until TASK-055).
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger("thinking_os.roles_state")


def resolve_agent_dir() -> str:
    """Agent-scoped state dir: $COS_AGENT_DIR or $COS_STATE_DIR/$COS_AGENT."""
    agent_dir = os.environ.get("COS_AGENT_DIR")
    if agent_dir:
        return agent_dir
    state_dir = os.environ.get("COS_STATE_DIR", ".coding-os")
    return os.path.join(state_dir, os.environ.get("COS_AGENT", "claude"))


def stamp_roles(chain: list[str], agent_dir: str | None = None) -> None:
    """Write the chain to .roles and the lead role to .role. Never raises."""
    target = agent_dir or resolve_agent_dir()
    try:
        Path(target).mkdir(parents=True, exist_ok=True)
        with open(os.path.join(target, ".roles"), "w", encoding="utf-8") as fh:
            json.dump(list(chain), fh)
        if chain:
            with open(os.path.join(target, ".role"), "w", encoding="utf-8") as fh:
                fh.write(str(chain[0]))
    except OSError as exc:
        # Fire-and-forget telemetry — a write error must never break compose.
        logger.debug("stamp_roles write failed: %s", exc)


# Tool/phase → preferred role. The active role advances as the agent moves
# through work phases (analyze → build → verify), so the banner reflects what
# the agent is DOING, not a frozen chain lead (TASK-057 F2.3). Each candidate
# is chosen only if it's actually IN the composed chain — we never invent a
# role the composer didn't pick.
_PHASE_ROLE_CANDIDATES: dict[str, tuple[str, ...]] = {
    # code edits → the building/fixing roles, best-match first
    "edit": ("implementer", "refactorer", "debugger", "architect"),
    # verification / tests → reviewer
    "verify": ("reviewer", "security_auditor"),
    # doc writes → documenter
    "doc": ("documenter",),
}


def advance_role(phase: str, agent_dir: str | None = None) -> str | None:
    """Set .role to the chain member best matching the current work phase.

    Reads the composed chain from .roles; picks the first phase-candidate role
    that is present in the chain; writes it to .role. Returns the chosen role
    (or None if no chain / no match). Never raises — fire-and-forget.
    """
    target = agent_dir or resolve_agent_dir()
    try:
        roles_path = os.path.join(target, ".roles")
        if not os.path.exists(roles_path):
            return None
        with open(roles_path, encoding="utf-8") as fh:
            chain = json.load(fh)
        if not isinstance(chain, list) or not chain:
            return None
        chain_str = [str(c) for c in chain]
        for cand in _PHASE_ROLE_CANDIDATES.get(phase, ()):  # ordered preference
            if cand in chain_str:
                with open(os.path.join(target, ".role"), "w", encoding="utf-8") as fh:
                    fh.write(cand)
                return cand
        return None
    except (OSError, ValueError) as exc:
        logger.debug("advance_role failed: %s", exc)
        return None
