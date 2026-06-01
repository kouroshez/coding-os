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
