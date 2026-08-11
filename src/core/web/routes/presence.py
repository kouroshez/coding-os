"""core.web.routes.presence — /api/presence/* live HUD summary.

The on-disk runtime readers and the context-window accounting moved to leaf
siblings; this module owns the router and the two payload shapes built from
them. Every helper is re-exported, so `from web.routes.presence import …` keeps
resolving for sessions.py and the Hub route.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends

from .._deps import make_metrics_dep, make_rate_limit_dep
from .._envelope import unwrap
from ._presence_context import (
    _CODEX_ROLLOUT_PATHS as _CODEX_ROLLOUT_PATHS,
    _codex_rollout_context,
    _codex_rollout_path as _codex_rollout_path,
    _context_pct_from_usage,
    _context_pct_from_used_tokens,
    _context_window,
    _effective_window as _effective_window,
    _latest_transcript_usage,
)
from ._presence_runtime import (
    _agent_runtime,
    _canonical_agents,
    _last_hook_event,
    _latest_claude_chat_uuid,
    _newest_marker as _newest_marker,
    _project_slug,
    _read_json as _read_json,
    _read_text as _read_text,
    _state_dir,
    _strip_session_prefix as _strip_session_prefix,
)

logger = logging.getLogger("coding_os.web.presence")

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

router = APIRouter(prefix="/api/presence", tags=["presence"])

# Per-agent fields surfaced to the HUD. The raw sessions/<sid>.json blob
# (_agent_runtime's "session") stays server-side — it carries absolute
# transcript paths + internal bookkeeping a read API must never leak. The UI
# PresenceAgent type (ui/src/lib/presence.ts) reads only these scalars.
_PRESENCE_NOW_FIELDS = ("agent", "session_id", "task", "skill_active", "model", "gate")


@router.get("/now")
def presence_now(
    _rl=Depends(make_rate_limit_dep("presence.now")),
    _m=Depends(make_metrics_dep("presence.now")),
):
    """Compact 'who is running, doing what, last hook fire' for the AppShell HUD."""
    from web._project_context import current_project_root  # type: ignore

    project = current_project_root()
    slug = _project_slug(project)
    state = _state_dir()
    canonical = _canonical_agents()

    agents: list[dict[str, Any]] = []
    if state.is_dir():
        for agent_id in canonical:
            agent_dir = state / agent_id
            snap = _agent_runtime(agent_dir, agent_id)
            if snap is None:
                continue
            agents.append({k: snap.get(k) for k in _PRESENCE_NOW_FIELDS})

    last_hook = _last_hook_event(state)
    chat_uuid = _latest_claude_chat_uuid(project)

    # Use the same presence math as `/api/board/list` so the AppShell HUD
    # and the Scrumban board agree on agent state.
    agent_states: dict[str, str] = {"human": "active"}
    try:
        from web.routes.board import _agent_state, _db_conn  # type: ignore

        conn = _db_conn()
        try:
            for agent_id in canonical:
                agent_states[agent_id] = _agent_state(conn, agent_id)
        finally:
            conn.close()
    except Exception as exc:
        logger.debug("agent_state lookup failed; using bare presence: %s", exc)

    return unwrap(
        json.dumps(
            {
                "ok": True,
                "data": {
                    "project_root": str(project),
                    "slug": slug,
                    "state_dir": str(state),
                    "agents": agents,
                    "agent_states": agent_states,
                    "last_hook": last_hook,
                    "current_chat_uuid": chat_uuid,
                    "meta": {"layer": "presence"},
                },
            }
        )
    )


@router.get("/agents")
def presence_agents(
    _rl=Depends(make_rate_limit_dep("presence.agents")),
    _m=Depends(make_metrics_dep("presence.agents")),
):
    """Unified per-agent live snapshot — model+gate+task+skill+role+chain+lifecycle+sdk_uuid in ONE call."""
    from web._project_context import current_project_root  # type: ignore

    project = current_project_root()
    slug = _project_slug(project)
    state = _state_dir()
    canonical = _canonical_agents()

    # Lifecycle state from the same SSOT the board uses.
    states: dict[str, str] = {}
    try:
        from web.routes.board import _agent_state, _db_conn  # type: ignore

        conn = _db_conn()
        try:
            for agent_id in canonical:
                states[agent_id] = _agent_state(conn, agent_id)
        finally:
            conn.close()
    except Exception as exc:
        logger.debug("agent_state lookup failed: %s", exc)

    try:
        from web.routes.roles import resolve_chain  # type: ignore
    except Exception:
        resolve_chain = None  # type: ignore

    agents: list[dict[str, Any]] = []
    if state.is_dir():
        for agent_id in canonical:
            snap = _agent_runtime(state / agent_id, agent_id)
            if snap is None:
                continue
            chain: list[str] = []
            role: str | None = None
            if resolve_chain is not None:
                try:
                    chain, role = resolve_chain(state, agent_id)
                except Exception as exc:
                    logger.debug("resolve_chain failed for %s: %s", agent_id, exc)
            sess = snap.get("session")
            sdk_uuid = sess.get("sdk_uuid") if isinstance(sess, dict) else None
            # Context-window % — Claude-only; honest null for adapters with no
            # usage signal. Primary source: used_tokens stamped on the Stop
            # path (TASK-255, no opt-in needed). Fallback: the opt-in snapshot
            # transcript tail (COS_SNAPSHOT_TRANSCRIPT=1).
            context_pct: float | None = None
            sid = snap.get("session_id")
            used_tokens = sess.get("used_tokens") if isinstance(sess, dict) else None
            context_window = _context_window(snap.get("model"))
            if used_tokens is not None:
                context_pct = _context_pct_from_used_tokens(used_tokens, snap.get("model"))
            if context_pct is None and sid:
                tpath = state / agent_id / "sessions" / "transcripts" / f"{sid}.jsonl"
                if tpath.exists():
                    usage = _latest_transcript_usage(tpath)
                    if usage:
                        context_pct = _context_pct_from_usage(usage, snap.get("model"))
            if context_pct is None:
                rollout = _codex_rollout_context(sdk_uuid)
                if rollout is not None:
                    used_tokens, context_window = rollout
                    context_pct = round(min(100.0, used_tokens / context_window * 100.0), 1)
            agents.append(
                {
                    "agent": agent_id,
                    "session_id": snap.get("session_id"),
                    "sdk_uuid": sdk_uuid,
                    "slug": slug,
                    "model": snap.get("model"),
                    "gate": snap.get("gate"),
                    "task": snap.get("task"),
                    "skill_active": snap.get("skill_active"),
                    "role": role,
                    "chain": chain,
                    "state": states.get(agent_id, "offline"),
                    "context_pct": context_pct,
                    "used_tokens": used_tokens,
                    "context_window": context_window,
                }
            )

    return unwrap(
        json.dumps(
            {
                "ok": True,
                "data": {
                    "project_root": str(project),
                    "state_dir": str(state),
                    "agents": agents,
                    "meta": {"layer": "presence"},
                },
            }
        )
    )


def cross_project_agents() -> list[dict[str, Any]]:
    """Per-project live-agent groups across EVERY registered project (TASK-437).

    Walks cli.registry and scopes each project to its OWN state dir + DB. A
    fresh sqlite handle is opened and closed within each iteration so no
    project's connection/state leaks into another (hub-architecture.md
    § Per-project backend keying — the exact hazard TASK-424 hardens)."""
    import sqlite3

    try:
        from cli.registry import load_registry  # type: ignore

        reg = load_registry()
    except Exception as exc:
        logger.debug("load_registry failed for cross-project agents: %s", exc)
        return []
    try:
        from web.routes.board import _agent_state  # type: ignore
    except Exception:
        _agent_state = None  # type: ignore
    try:
        from web.routes.roles import resolve_chain  # type: ignore
    except Exception:
        resolve_chain = None  # type: ignore

    canonical = _canonical_agents()
    groups: list[dict[str, Any]] = []
    for entry in reg.projects:
        try:
            project_root = Path(entry.path).resolve()
        except OSError:
            continue
        state = project_root / ".coding-os"
        if not state.is_dir():
            continue
        # Per-project lifecycle state from a connection scoped to THIS project's
        # DB only — opened + closed here so the handle never escapes the loop.
        states: dict[str, str] = {}
        db_file = state / "coding-os.db"
        if _agent_state is not None and db_file.exists():
            conn = None
            try:
                conn = sqlite3.connect(str(db_file))
                for agent_id in canonical:
                    states[agent_id] = _agent_state(conn, agent_id)
            except Exception as exc:
                logger.debug("agent_state for %s failed: %s", entry.slug, exc)
            finally:
                if conn is not None:
                    conn.close()

        agents: list[dict[str, Any]] = []
        for agent_id in canonical:
            snap = _agent_runtime(state / agent_id, agent_id)
            if snap is None:
                continue
            chain: list[str] = []
            role: str | None = None
            if resolve_chain is not None:
                try:
                    chain, role = resolve_chain(state, agent_id)
                except Exception as exc:
                    logger.debug("resolve_chain failed for %s/%s: %s", entry.slug, agent_id, exc)
            sess = snap.get("session")
            sdk_uuid = sess.get("sdk_uuid") if isinstance(sess, dict) else None
            agents.append(
                {
                    "agent": agent_id,
                    "session_id": snap.get("session_id"),
                    "sdk_uuid": sdk_uuid,
                    "slug": entry.slug,
                    "model": snap.get("model"),
                    "gate": snap.get("gate"),
                    "task": snap.get("task"),
                    "skill_active": snap.get("skill_active"),
                    "role": role,
                    "chain": chain,
                    "state": states.get(agent_id, "offline"),
                }
            )
        if agents:
            groups.append({"slug": entry.slug, "project_root": str(project_root), "agents": agents})
    return groups
