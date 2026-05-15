"""Coding OS — Project Trajectory tools (Phase EVO)."""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger("coding_os.tools.trajectory")

# Valid root_cause values for failure anatomy (enforced at application level)
VALID_ROOT_CAUSES = frozenset({
    "wrong_model",
    "scope_too_large",
    "missing_context",
    "tool_failure",
    "spec_ambiguity",
    "env_mismatch",
    "other",
})


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _table_ready(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='project_trajectory'"
    ).fetchone()
    return row is not None


# ---------------------------------------------------------------------------
# trajectory_snapshot — write
# ---------------------------------------------------------------------------

def trajectory_snapshot(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    phase: str = "",
    current_focus: str = "",
    architectural_decisions: Optional[list] = None,
    anti_patterns_discovered: Optional[list] = None,
    open_questions: Optional[list] = None,
    next_logical_step: str = "",
    confidence: float = 0.7,
) -> dict:
    """Persist a project trajectory snapshot for the current session."""
    if not _table_ready(conn):
        return {"status": "skipped", "reason": "project_trajectory table not found (run migration v24)"}

    if not session_id:
        return {"status": "error", "reason": "session_id required"}

    confidence = max(0.0, min(1.0, float(confidence)))

    ad_json  = json.dumps(architectural_decisions or [])
    apd_json = json.dumps(anti_patterns_discovered or [])
    oq_json  = json.dumps(open_questions or [])

    prev = conn.execute(
        "SELECT id FROM project_trajectory ORDER BY id DESC LIMIT 1"
    ).fetchone()
    supersedes_id = prev[0] if prev else None

    cur = conn.execute(
        "INSERT INTO project_trajectory "
        "(session_id, phase, current_focus, architectural_decisions, "
        " anti_patterns_discovered, open_questions, next_logical_step, "
        " confidence, created_at, supersedes_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            session_id,
            phase or None,
            current_focus or None,
            ad_json,
            apd_json,
            oq_json,
            next_logical_step or None,
            confidence,
            _now_iso(),
            supersedes_id,
        ),
    )
    conn.commit()
    row_id = cur.lastrowid
    logger.debug("trajectory_snapshot: id=%s supersedes=%s", row_id, supersedes_id)
    return {"status": "ok", "id": row_id, "supersedes_id": supersedes_id}


# ---------------------------------------------------------------------------
# trajectory_read — read
# ---------------------------------------------------------------------------

def trajectory_read(
    conn: sqlite3.Connection,
    *,
    limit: int = 1,
) -> dict:
    """Return the most recent project trajectory snapshot(s)."""
    if not _table_ready(conn):
        return {"snapshots": [], "count": 0,
                "note": "project_trajectory table not found (run migration v24)"}

    limit = max(1, min(20, int(limit)))

    rows = conn.execute(
        "SELECT id, session_id, phase, current_focus, "
        "       architectural_decisions, anti_patterns_discovered, "
        "       open_questions, next_logical_step, confidence, "
        "       created_at, supersedes_id "
        "FROM project_trajectory "
        "ORDER BY id DESC "
        "LIMIT ?",
        (limit,),
    ).fetchall()

    snapshots = []
    for r in rows:
        snap: dict[str, Any] = dict(r)
        for field in ("architectural_decisions", "anti_patterns_discovered", "open_questions"):
            try:
                snap[field] = json.loads(snap[field] or "[]")
            except (json.JSONDecodeError, TypeError):
                snap[field] = []
        snapshots.append(snap)

    return {"snapshots": snapshots, "count": len(snapshots)}


# ---------------------------------------------------------------------------
# trajectory_digest_line — compact line for digest.md (≤ 300 chars)
# ---------------------------------------------------------------------------

def trajectory_digest_line(conn: sqlite3.Connection) -> str:
    """Return a compact single-paragraph trajectory summary for digest.md."""
    if not _table_ready(conn):
        return ""
    try:
        row = conn.execute(
            "SELECT phase, current_focus, next_logical_step, open_questions "
            "FROM project_trajectory "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()
    except sqlite3.OperationalError:
        return ""

    if not row:
        return ""

    parts = []
    if row["phase"]:
        parts.append(row["phase"])
    if row["current_focus"]:
        parts.append(f"Focus: {row['current_focus']}")
    if row["next_logical_step"]:
        parts.append(f"Next: {row['next_logical_step']}")
    try:
        oqs = json.loads(row["open_questions"] or "[]")
        if oqs and isinstance(oqs, list) and oqs[0]:
            first = oqs[0] if isinstance(oqs[0], str) else oqs[0].get("question", "")
            if first:
                parts.append(f"Open: {first}")
    except (json.JSONDecodeError, TypeError, AttributeError):
        pass

    line = " · ".join(parts)
    return line[:290]  # leave margin for section header
