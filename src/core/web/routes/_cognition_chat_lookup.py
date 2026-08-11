"""Transcript-resolution helpers behind the chat read routes.

Answering "which agent owns this session id?" and "is there a dispatched
sub-session transcript for it?" reads persisted state, while the routes above
shape the response — two different reasons to change. Sibling state is reached
through the `cognition` module object, never a from-import, so the accessors a
test patches on that module are the ones these helpers call.
"""

from __future__ import annotations

import json
import logging
import sqlite3

from . import cognition as _cog

logger = logging.getLogger(__name__)


def _session_agent_hints(session_id: str) -> set[str]:
    hints: set[str] = set()
    state = _cog._state_dir()
    if not state.is_dir():
        return hints
    for agent_dir in state.iterdir():
        sessions_dir = agent_dir / "sessions"
        if not sessions_dir.is_dir():
            continue
        for path in sessions_dir.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if payload.get("sdk_uuid") == session_id:
                hints.add(str(payload.get("agent") or agent_dir.name))
    return hints


def _dispatch_transcript_chat(session_id: str) -> dict | None:
    # Fall back to a dispatched sub-session's persisted transcript when the live
    # Claude SDK session no longer exists on disk — resolves the dead sdk_uuid
    # modal link (TASK-667). Keyed on formula_dispatches.sub_session_id (= the
    # SDK session_id the UI links from). Read-only, fail-open.
    db_path = _cog._db_path()
    if not db_path:
        return None
    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT formula_id, status, model, raw_transcript "
                "FROM formula_dispatches "
                "WHERE sub_session_id = ? AND raw_transcript IS NOT NULL "
                "ORDER BY ts DESC LIMIT 1",
                (session_id,),
            ).fetchone()
    except sqlite3.Error as exc:
        logger.debug("dispatch transcript fallback query failed: %s", exc)
        return None
    if row is None or not row["raw_transcript"]:
        return None
    return {
        "session": {
            "session_id": session_id,
            "source": "dispatch_transcript",
            "formula_id": row["formula_id"],
            "model": row["model"],
            "status": row["status"],
            # Mirror the fields ChatView reads (custom_title ?? summary ?? id;
            # git_branch/cwd/last_modified in the header) so the fallback renders
            # a real title instead of the raw session id, and reads no undefined.
            "custom_title": f"dispatch: {row['formula_id']} ({row['status']})",
            "summary": None,
            "first_prompt": None,
            "last_modified": None,
            "file_size": None,
            "git_branch": None,
            "cwd": None,
            "tag": None,
            "created_at": None,
        },
        "messages": [
            {
                "uuid": None,
                "session_id": session_id,
                "type": "assistant",
                "role": "assistant",
                "model": row["model"],
                "stop_reason": None,
                "usage": None,
                "blocks": [{"type": "text", "text": row["raw_transcript"]}],
                "parent_tool_use_id": None,
            }
        ],
        "count": 1,
        "offset": 0,
        "meta": {"layer": "cognition", "source": "formula_dispatches"},
    }
