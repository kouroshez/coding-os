"""Per-agent / per-session presence state — shared by /api/board/list,
/api/stream/events, and the cos_presence_query MCP tool.

Single source of truth so the HTTP envelope and the MCP envelope can
never disagree on whether a session is `active` / `working` /
`present` / `offline`.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Tunables — bumped during P3 (live-agents pill rework). Keep them in
# this module so the test matrix and docs have one place to look.
ACTIVE_WINDOW_SECS = 90
WORKING_WINDOW_SECS = 30 * 60
PRESENT_WINDOW_SECS = 30 * 60

STATE_RANK: dict[str, int] = {
    "offline": 0,
    "present": 1,
    "working": 2,
    "active": 3,
}


def pid_alive(pid: int) -> bool:
    """True iff `pid` is a process alive on this host."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def session_files(presence_dir: Path) -> list[Path]:
    """List `<sid>.json` files under presence_dir; missing dir → []."""
    if not presence_dir.is_dir():
        return []
    try:
        return [p for p in presence_dir.iterdir() if p.suffix == ".json" and p.is_file()]
    except OSError as exc:
        logger.debug("presence dir read failed for %s: %s", presence_dir, exc)
        return []


def session_presence(data: dict, now: int) -> str:
    """Compute the presence verdict for ONE session payload."""
    if data.get("ended_at") is not None:
        return "offline"
    last_tool = data.get("last_tool_at")
    last_prompt = data.get("last_prompt_at")
    last_stop = data.get("last_stop_at")

    if isinstance(last_tool, int) and now - last_tool <= ACTIVE_WINDOW_SECS:
        return "active"

    pid = int(data.get("pid") or 0)
    if not pid_alive(pid):
        return "offline"

    prompt_in_flight = isinstance(last_prompt, int) and (
        not isinstance(last_stop, int) or last_stop < last_prompt
    )
    if (
        prompt_in_flight
        and isinstance(last_prompt, int)
        and now - last_prompt <= WORKING_WINDOW_SECS
    ):
        return "working"
    if isinstance(last_prompt, int) and now - last_prompt <= PRESENT_WINDOW_SECS:
        return "present"
    if isinstance(last_tool, int) and now - last_tool <= PRESENT_WINDOW_SECS:
        return "present"
    started = data.get("started_at") or 0
    if isinstance(started, int) and now - int(started) <= PRESENT_WINDOW_SECS:
        return "present"
    return "offline"


def promote(best: str, candidate: str) -> str:
    return candidate if STATE_RANK[candidate] > STATE_RANK[best] else best


def agent_state(presence_dir: Path, now: int | None = None) -> str:
    """Aggregate the highest-rank verdict across all sessions for an agent."""
    if now is None:
        now = int(time.time())
    best = "offline"
    for path in session_files(presence_dir):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.debug("skipping corrupt presence file %s: %s", path, exc)
            continue
        verdict = session_presence(data, now)
        if verdict == "active":
            return "active"
        best = promote(best, verdict)
    return best


def session_inventory(
    agent: str, presence_dir: Path, now: int | None = None
) -> list[dict[str, Any]]:
    """Per-session rows for `agent`; offline sessions are filtered out."""
    if now is None:
        now = int(time.time())
    rows: list[dict[str, Any]] = []
    for path in session_files(presence_dir):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        verdict = session_presence(data, now)
        if verdict == "offline":
            continue
        rows.append(
            {
                "agent": agent,
                "sid": data.get("session_id") or path.stem,
                "state": verdict,
                "pid": int(data.get("pid") or 0),
                "started_at": data.get("started_at"),
                "last_prompt_at": data.get("last_prompt_at"),
                "last_tool_at": data.get("last_tool_at"),
                "last_stop_at": data.get("last_stop_at"),
            }
        )
    rows.sort(
        key=lambda r: (
            -STATE_RANK.get(r["state"], 0),
            -(r.get("last_tool_at") or r.get("last_prompt_at") or r.get("started_at") or 0),
        )
    )
    return rows
