"""board_os workflow — WIP cap counting.

in_progress is a per-worker focus cap; testing and emergency stay board-global.
"""

from __future__ import annotations

import logging
import sqlite3

from board_os.config import ScrumbanConfig

from ._workflow_types import _WIP_COLUMN_MAP, WipState

logger = logging.getLogger("coding_os.board_os.workflow")


def _is_shared_pid_session(session: str | None) -> bool:
    # resolve_agent_session's last-resort synthetic is ses-<agent>-pid<PID>.
    # For the long-lived MCP server that PID is shared by ALL panels, so a
    # per-session cap keyed on it is NOT panel-isolated.
    if not session or not session.startswith("ses-"):
        return False
    idx = session.rfind("-pid")
    return idx != -1 and session[idx + len("-pid") :].isdigit()


def check_wip(
    conn: sqlite3.Connection,
    config: ScrumbanConfig,
    *,
    agent_session: str | None = None,
) -> WipState:
    # in_progress is a per-worker focus cap: when per_session_wip is on
    # and a session is known, count only that session's in_progress
    # tasks so concurrent sessions don't block each other on a global
    # cap. testing / emergency stay board-global (queue / SEV limits).
    per_session = bool(config.workflow_policy.per_session_wip and agent_session)
    if per_session and _is_shared_pid_session(agent_session):
        # Attribution fell back to the shared MCP-server PID synthetic — surface
        # it rather than silently applying an in_progress cap that is shared
        # across sibling panels instead of being per-panel.
        logger.warning(
            "per-session WIP cap degraded: agent_session %r is a shared "
            "ses-<agent>-pid<PID> synthetic (panel attribution unresolved); "
            "the in_progress cap is shared across sibling panels, not per-panel.",
            agent_session,
        )
    counts: dict[str, int] = {}
    for status in _WIP_COLUMN_MAP.values():
        if per_session and status == "in_progress":
            row = conn.execute(
                "SELECT COUNT(*) FROM tasks WHERE status = ? AND agent_session = ?",
                (status, agent_session),
            ).fetchone()
        else:
            row = conn.execute("SELECT COUNT(*) FROM tasks WHERE status = ?", (status,)).fetchone()
        counts[status] = int(row[0]) if row else 0
    caps = {
        "in_progress": config.wip_limits.in_progress,
        "testing": config.wip_limits.testing,
        "emergency": config.wip_limits.emergency,
    }
    violations = tuple(col for col in caps if counts.get(col, 0) > caps[col])
    return WipState(counts=counts, caps=caps, violations=violations)
