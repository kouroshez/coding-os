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


def record_compose_traces(chain, session_id: str, agent_dir: str | None = None) -> None:
    """Emit the branch + compose_done trace events for a composed chain.

    Shared by the MCP tool ``cos_compose_chain`` and the auto-compose hook
    (auto_compose.py) so the two call sites never drift on the events the Hub
    ``/api/roles`` panel reads — ``compose_done`` (chain + planned view) plus
    the source-specific branch event for trace replay. ``chain`` is a
    ComposedChain (duck-typed). ``agent_dir`` is None for both callers so the
    trace lands in the agent-level traces dir (``$COS_AGENT_DIR``) the panel
    scans — never the per-panel marker dir. Never raises (fire-and-forget).
    """
    try:
        import tracing
    except ImportError as exc:
        logger.debug("record_compose_traces: tracing unavailable: %s", exc)
        return
    sid = session_id or "anon"
    target = Path(agent_dir) if agent_dir else None
    try:
        source = getattr(chain, "source", "") or ""
        chain_list = [str(c) for c in (getattr(chain, "chain", None) or [])]
        if source == "preset":
            tracing.emit(sid, "preset_matched", {
                "preset_id": getattr(chain, "preset_id", None),
                "preset_version": getattr(chain, "preset_version", None),
                "chain": chain_list,
                "effective_threshold": getattr(chain, "effective_threshold", None),
            }, agent_dir=target)
        elif source == "situation":
            tracing.emit(sid, "situation_override", {
                "situation_id": getattr(chain, "situation_id", None),
                "chain": chain_list,
            }, agent_dir=target)
        elif source == "composer":
            tracing.emit(sid, "composer_fallback", {
                "chain": chain_list,
                "activations": [a.model_dump() for a in (getattr(chain, "activations", None) or [])],
            }, agent_dir=target)
        else:
            tracing.emit(sid, "hard_fallback", {
                "chain": chain_list,
                "reason": getattr(chain, "reason", None),
            }, agent_dir=target)
        tracing.emit(sid, "compose_done", {
            "chain": chain_list,
            "source": source,
            "preset_id": getattr(chain, "preset_id", None),
        }, agent_dir=target)
    except Exception as exc:  # fire-and-forget telemetry — never break compose
        logger.debug("record_compose_traces emit failed: %s", exc)


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
