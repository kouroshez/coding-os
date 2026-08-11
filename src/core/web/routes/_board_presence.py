"""core.web.routes._board_presence — per-agent liveness for the board.

Presence math lives in `board_os.presence` (SSOT); this module binds it to the
per-project `.coding-os/<agent>/sessions/` directory and keeps the legacy
DB-only fallback for projects that pre-date the presence hook.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

# Presence windows + state-rank live in board_os.presence (SSOT).  Re-
# export the constants the tests still reference.
from board_os.presence import (
    ACTIVE_WINDOW_SECS as _ACTIVE_WINDOW_SECS,  # noqa: F401  (re-exported)
    agent_state as _agent_state_fs,
    pid_alive as _pid_alive_fn,
    session_inventory as _session_inventory_fs,
    session_presence as _session_presence_fn,
)

from ._board_shared import _CORE_DIR as _CORE_DIR

_DB_FALLBACK_WINDOW_SECS = 300  # legacy DB-only signal window


# `_pid_alive` is re-exported from board_os.presence so legacy callers
# inside this module keep working unchanged.
_pid_alive = _pid_alive_fn


def _presence_dir(agent: str) -> Path:
    from web._project_context import current_project_root

    return current_project_root() / ".coding-os" / agent / "sessions"


def _presence_files(agent: str) -> list[Path]:
    """Return the per-session presence JSON files for this agent."""
    from board_os.presence import session_files

    return session_files(_presence_dir(agent))


# Per-agent / per-session presence math lives in board_os.presence.
# Thin filesystem-bound wrappers below resolve the per-project
# .coding-os/<agent>/sessions/ directory and delegate.
def _presence_state(agent: str) -> str:
    return _agent_state_fs(_presence_dir(agent))


def _session_inventory(agent: str) -> list[dict]:
    return _session_inventory_fs(agent, _presence_dir(agent))


# `_session_presence` is preserved as a stable name for any in-tree
# tests that imported it directly.
_session_presence = _session_presence_fn


def _agent_active_from_db(conn: sqlite3.Connection, agent: str) -> bool:
    """Legacy signal: recent task transition or in-progress task ownership.

    Retained as a fallback so projects that pre-date the presence hook
    (no .coding-os/<agent>/sessions/ directory) still get SOMETHING
    useful on the board.  New deployments should rely on _presence_state.
    """
    session_like = f"%{agent}%"
    recent_transition = conn.execute(
        """
        SELECT 1
        FROM task_status_history
        WHERE agent_session LIKE ?
          AND transitioned_at >= CAST(strftime('%s','now') AS INTEGER) - ?
        LIMIT 1
        """,
        (session_like, _DB_FALLBACK_WINDOW_SECS),
    ).fetchone()
    if recent_transition:
        return True

    active_owned_task = conn.execute(
        """
        SELECT 1
        FROM tasks
        WHERE status IN ('in_progress', 'testing', 'emergency')
          AND agent_session LIKE ?
        LIMIT 1
        """,
        (session_like,),
    ).fetchone()
    return bool(active_owned_task)


def _agent_state(conn: sqlite3.Connection, agent: str) -> str:
    """Preferred signal: presence files.  Falls back to DB for legacy."""
    state = _presence_state(agent)
    if state != "offline":
        return state
    if _agent_active_from_db(conn, agent):
        return "present"
    return "offline"
