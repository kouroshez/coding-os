"""core.web.routes.sessions - read-only presence API.

Surfaces the per-agent presence files written by adapters/claude/sdk_dispatcher.py
(`_presence_write`) and `core/hooks/agent-presence.sh`. No POST, no chat
endpoints — that scope ships separately. This route exists so the Hub UI
can show "who is alive right now" without reading filesystem state in
the browser.

Path: GET /api/sessions/active
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path

from fastapi import APIRouter

_CORE_DIR = Path(__file__).resolve().parents[3]
if str(_CORE_DIR) not in sys.path:
    sys.path.insert(0, str(_CORE_DIR))

from web._project_context import current_project_root  # noqa: E402

logger = logging.getLogger("coding_os.web.sessions")

router = APIRouter(prefix="/api/sessions", tags=["sessions"])

PRESENCE_TTL_S = 300


def _project_state_dir() -> Path:
    base = os.environ.get("COS_STATE_DIR")
    if base:
        return Path(base).resolve()
    return current_project_root() / ".coding-os"


def _pid_alive(pid: int | None) -> bool:
    if not pid or pid <= 0:
        return False
    try:
        os.kill(int(pid), 0)
    except OSError:
        return False
    except (TypeError, ValueError):
        return False
    return True


def _classify(presence: dict, now: int) -> str:
    last_tool = presence.get("last_tool_at") or 0
    last_prompt = presence.get("last_prompt_at") or 0
    last_stop = presence.get("last_stop_at") or 0
    ended = presence.get("ended_at") or 0
    pid = presence.get("pid")
    if ended:
        return "ended"
    if not _pid_alive(pid):
        return "offline"
    most_recent = max(last_tool, last_prompt, last_stop)
    if most_recent and (now - most_recent) <= 30:
        return "active"
    if most_recent and (now - most_recent) <= PRESENCE_TTL_S:
        return "present"
    return "idle"


def _load_presence_for_agent(agent_dir: Path, agent: str, now: int) -> list[dict]:
    sessions_dir = agent_dir / "sessions"
    if not sessions_dir.is_dir():
        return []
    # The agent's `session-id` marker names its one live session. A row
    # matching it is genuinely current — never a recycled-PID leftover —
    # so the dashboard can trust it as live even when activity is stale.
    try:
        current_sid = (agent_dir / "session-id").read_text(encoding="utf-8").strip() or None
    except (OSError, UnicodeDecodeError):
        current_sid = None
    out: list[dict] = []
    try:
        candidates = sorted(sessions_dir.glob("*.json"))
    except OSError as exc:
        logger.debug("presence dir scan failed for %s: %s", agent, exc)
        return out
    for path in candidates:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.debug("presence read failed %s: %s", path, exc)
            continue
        if not isinstance(data, dict):
            continue
        data.setdefault("agent", agent)
        data["state"] = _classify(data, now)
        data["is_current"] = current_sid is not None and data.get("session_id") == current_sid
        data["presence_file"] = str(path)
        out.append(data)
    return out


@router.get("/active")
async def list_active_sessions():
    """Return all known agent presence records grouped by lifecycle state.

    State values:
      - active   : tool/prompt activity within last 30 s and pid alive
      - present  : activity within PRESENCE_TTL_S (default 300 s) and pid alive
      - idle     : pid alive but no recent activity
      - offline  : pid not alive
      - ended    : ended_at recorded

    Each record also carries `is_current` — true when its session_id
    matches the agent's `session-id` marker (the agent's live session).
    """
    state_dir = _project_state_dir()
    if not state_dir.is_dir():
        return {"ok": True, "data": {"sessions": [], "counts": {}, "state_dir": str(state_dir)}}

    now = int(time.time())
    sessions: list[dict] = []
    for child in state_dir.iterdir():
        if not child.is_dir():
            continue
        if child.name.startswith("."):
            continue
        if child.name in {"locks", "templates", "logs", "traces"}:
            continue
        sessions.extend(_load_presence_for_agent(child, child.name, now))

    counts: dict[str, int] = {}
    for s in sessions:
        st = s.get("state", "unknown")
        counts[st] = counts.get(st, 0) + 1

    sessions.sort(
        key=lambda s: (
            0 if s.get("state") == "active" else 1 if s.get("state") == "present" else 2,
            -(s.get("last_tool_at") or s.get("last_prompt_at") or 0),
        )
    )

    return {
        "ok": True,
        "data": {
            "sessions": sessions,
            "counts": counts,
            "now": now,
            "ttl_s": PRESENCE_TTL_S,
            "state_dir": str(state_dir),
        },
    }
