"""Board-card shaping — the row SELECT, the card dict, and the staleness flags.

How a task row becomes a card the board renders changes with the UI's needs;
how ids are minted or forge links parsed does not. Purely derivational: nothing
here writes board state. A leaf — it imports no other board_os MCP module.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import time

logger = logging.getLogger("coding_os.board_os.mcp_tools")


def _status_dwell_seconds(now: float, started_at, last_transition_at) -> int | None:
    # Reuse the reclaim derivation (max of started_at and last transition) so
    # dwell, reclaim idle, and SLA staleness share one "last activity" definition.
    last = max(int(started_at or 0), int(last_transition_at or 0))
    if last <= 0:
        return None
    return max(0, int(now - last))


def _humanize_duration(seconds: int | None) -> str | None:
    if seconds is None:
        return None
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h"
    return f"{seconds // 86400}d"


def _task_card(row: sqlite3.Row | tuple) -> dict:
    started_at = row[11] if len(row) > 11 else None
    completed_at = row[12] if len(row) > 12 else None
    last_transition_at = row[13] if len(row) > 13 else None
    dwell = _status_dwell_seconds(time.time(), started_at, last_transition_at)
    return {
        "id": row[0],
        "title": row[1],
        "swimlane": row[2] or "",
        "kind": row[3] or "",
        "epic": row[4],
        "labels": json.loads(row[5] or "[]"),
        "status": row[6],
        "priority": row[7] or "P2",
        "appetite": row[8] or "1d",
        "agent_session": row[9],
        "last_log_line": _last_log_line(row[10]),
        "completion_evidence": _completion_evidence(row[10]),
        "started_at": started_at,
        "completed_at": completed_at,
        "last_transition_at": last_transition_at,
        "status_dwell_seconds": dwell,
        "status_dwell_human": _humanize_duration(dwell),
    }


def _sla_threshold_seconds(status: str, config) -> int | None:
    if config is None:
        return None
    policy = config.workflow_policy
    hours = {
        "in_progress": policy.in_progress_sla_hours,
        "testing": policy.testing_sla_hours,
        "blocked": policy.blocked_sla_hours,
    }.get(status)
    if hours is not None:
        return hours * 3600 if hours > 0 else None
    if status == "icebox":
        return policy.icebox_stale_days * 86400 if policy.icebox_stale_days > 0 else None
    return None


def _flag_stale(card: dict, config) -> dict:
    # Observability only — never mutates board state. Mutates the card dict in
    # place and returns it so callers can map over a list.
    if card.get("status") == "icebox" and card.get("completion_evidence"):
        # Zombie: the work log claims finished work but the card never left
        # icebox — surface it on every board render, independent of any SLA.
        card["stale"] = True
        card["stale_reason"] = (
            "icebox card carries completion evidence (zombie) — "
            "run cos_task_reconcile, then lifecycle it through complete"
        )
        return card
    threshold = _sla_threshold_seconds(card.get("status", ""), config)
    dwell = card.get("status_dwell_seconds")
    if threshold is not None and dwell is not None and dwell > threshold:
        card["stale"] = True
        card["stale_reason"] = (
            f"{card['status']} {card.get('status_dwell_human')} > SLA "
            f"{_humanize_duration(threshold)}"
        )
    else:
        card["stale"] = False
        card["stale_reason"] = None
    return card


_COMPLETION_EVIDENCE_RE = re.compile(
    r"commit(?:ted)?\s+[0-9a-f]{7,40}"
    r"|implemented\b.{0,40}\bverified"
    r"|verified\b.{0,40}\bimplemented",
    re.IGNORECASE,
)


def _completion_evidence(work_log_json: str | None) -> bool:
    # Heuristic over the cached work-log lines: a linked commit sha or an
    # "implemented … verified" claim is evidence of finished work. Used only
    # for observability (zombie flag + reconcile triage), never for gating.
    if not work_log_json:
        return False
    return bool(_COMPLETION_EVIDENCE_RE.search(str(work_log_json)))


def _last_log_line(work_log_json: str | None) -> str | None:
    if not work_log_json:
        return None
    try:
        lines = json.loads(work_log_json)
    except json.JSONDecodeError:
        return None
    return lines[-1] if lines else None


_BOARD_SELECT = (
    "SELECT task_id, title, swimlane, kind, epic, labels_json, "
    "       status, priority, appetite, agent_session, work_log_last_5, "
    "       started_at, completed_at, "
    # last_transition_at (row[13]): the most recent status-change time from
    # history. Correlated subquery keeps the column appended LAST so existing
    # positional readers (retro r[11]/r[12]) are unaffected. Powers the board
    # time dimension (status_dwell_seconds) — RC5 of the 2026-06-05
    # task-lifecycle review.
    "       (SELECT MAX(h.transitioned_at) FROM task_status_history h "
    "        WHERE h.task_id = tasks.task_id) AS last_transition_at "
    "FROM tasks"
)
