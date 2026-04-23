"""core.web.routes.stream — /api/stream/events SSE for live board updates.

PURPOSE: Poll docs/tasks/ for TASK-*.md mtime changes and push SSE events so
         the SPA board page stays live without polling REST endpoints.
INPUT:   HTTP GET (EventSource connection), env COS_WEB_SSE_POLL_MS.
OUTPUT:  Server-Sent Events: task-updated {task_id, status} on change;
         heartbeat every 15 seconds.
DEPENDENCIES: fastapi, sse-starlette, asyncio, pathlib.
NOTES:  This is a simple mtime-polling SSE, not a full pubsub. For high
        throughput, replace with inotify/watchdog in a future slice.
        Poll interval: COS_WEB_SSE_POLL_MS env var (default 2000ms).
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import AsyncGenerator

from fastapi import APIRouter

_CORE_DIR = Path(__file__).resolve().parents[3]
if str(_CORE_DIR) not in sys.path:
    sys.path.insert(0, str(_CORE_DIR))

router = APIRouter(prefix="/api/stream", tags=["stream"])

_TASK_RE = re.compile(r"^TASK-(\d+)")
_HEARTBEAT_INTERVAL = 15.0  # seconds


def _tasks_dir() -> Path:
    """Resolve the docs/tasks directory.

    PURPOSE: Find where TASK-*.md files live for polling.
    INPUT:   COS_PROJECT_ROOT env var, fallback to cwd.
    OUTPUT:  Path to docs/tasks/.
    DEPENDENCIES: os.environ.
    NOTES:   Returns the path even when it doesn't exist; callers check exists().
    """
    root = Path(os.environ.get("COS_PROJECT_ROOT") or os.getcwd()).resolve()
    return root / "docs" / "tasks"


def _poll_interval_secs() -> float:
    """Read COS_WEB_SSE_POLL_MS from env, default 2000ms.

    PURPOSE: Allow runtime tuning of SSE poll frequency.
    INPUT:   COS_WEB_SSE_POLL_MS env var.
    OUTPUT:  float seconds.
    DEPENDENCIES: os.environ.
    NOTES:   Clamped to [0.5, 30] to prevent abuse.
    """
    raw = os.environ.get("COS_WEB_SSE_POLL_MS", "2000")
    try:
        ms = float(raw)
    except ValueError:
        ms = 2000.0
    return max(0.5, min(30.0, ms / 1000.0))


def _read_task_meta(path: Path) -> dict[str, str | None]:
    """Read the status and agent_session fields from a TASK-*.md frontmatter.

    PURPOSE: Extract metadata without parsing full YAML.
    INPUT:   path — the TASK-*.md file.
    OUTPUT:  dict with status and agent_session.
    DEPENDENCIES: pathlib.
    NOTES:   Uses simple regex to avoid yaml dep in the hot path.
    """
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
        m_status = re.search(r"^status:\s*(\S+)", content, re.MULTILINE)
        m_agent = re.search(r"^agent_session:\s*(\S+)", content, re.MULTILINE)
        return {
            "status": m_status.group(1).strip('"\'') if m_status else None,
            "agent_session": m_agent.group(1).strip('"\'') if m_agent else None,
        }
    except Exception:  # noqa: BLE001 — always return something
        return {"status": None, "agent_session": None}


async def _sse_event(event_type: str, data: dict) -> str:
    """Format a single SSE event string.

    PURPOSE: Produce the SSE wire format for a single event.
    INPUT:   event_type — SSE event name; data — JSON-serializable dict.
    OUTPUT:  SSE-formatted string with trailing double newline.
    DEPENDENCIES: json.
    NOTES:   The double newline is required by the SSE spec to flush the event.
    """
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


async def _event_generator() -> AsyncGenerator[str, None]:
    """Poll docs/tasks/ and yield SSE events.

    PURPOSE: Core SSE generator — monitors task files and emits change events.
    INPUT:   none (uses module-level constants).
    OUTPUT:  Async generator of SSE event strings.
    DEPENDENCIES: asyncio, pathlib.
    NOTES:   Emits heartbeat every 15s to keep the connection alive through
             load balancers that time out idle connections.
    """
    tasks_dir = _tasks_dir()
    poll = _poll_interval_secs()
    last_mtimes: dict[str, float] = {}
    last_heartbeat = time.monotonic()

    # Emit an initial connected event so the client knows the stream is up.
    yield await _sse_event("connected", {"message": "SSE stream connected", "poll_ms": int(poll * 1000)})

    while True:
        await asyncio.sleep(poll)

        now = time.monotonic()
        # Heartbeat every 15 seconds.
        if now - last_heartbeat >= _HEARTBEAT_INTERVAL:
            yield await _sse_event("heartbeat", {"ts": int(time.time())})
            last_heartbeat = now

        if not tasks_dir.exists():
            continue

        for md_file in tasks_dir.glob("TASK-*.md"):
            try:
                mtime = md_file.stat().st_mtime
            except OSError:
                continue

            fname = md_file.name
            prev_mtime = last_mtimes.get(fname)

            if prev_mtime is None:
                # First time we see this file — record but don't emit.
                last_mtimes[fname] = mtime
                continue

            if mtime != prev_mtime:
                last_mtimes[fname] = mtime
                m = _TASK_RE.match(fname)
                task_id = f"TASK-{m.group(1)}" if m else fname.replace(".md", "")
                meta = _read_task_meta(md_file)
                yield await _sse_event(
                    "task-updated",
                    {
                        "task_id": task_id,
                        "status": meta["status"],
                        "agent_session": meta["agent_session"],
                        "ts": int(time.time()),
                    },
                )


@router.get("/events")
async def sse_events():
    """SSE endpoint for live board task updates.

    PURPOSE: Push task-updated events to connected SPA clients via SSE.
    INPUT:   HTTP GET (EventSource connection, no params).
    OUTPUT:  text/event-stream with task-updated and heartbeat events.
    DEPENDENCIES: sse_starlette.sse.EventSourceResponse, _event_generator.
    NOTES:   Uses sse-starlette for EventSourceResponse; falls back to a
             streaming plain response if the package is unavailable.
    """
    try:
        from sse_starlette.sse import EventSourceResponse  # type: ignore

        async def _gen():
            async for chunk in _event_generator():
                # EventSourceResponse expects dicts or strings.
                yield chunk

        return EventSourceResponse(_gen())
    except ImportError:
        # Fallback: plain streaming response.
        from fastapi.responses import StreamingResponse

        async def _plain_gen():
            async for chunk in _event_generator():
                yield chunk.encode("utf-8")

        return StreamingResponse(
            _plain_gen(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
