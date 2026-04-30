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
import logging
import os
import re
import sqlite3
import sys
import time
from pathlib import Path
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from .._deps import make_metrics_dep, make_rate_limit_dep

_CORE_DIR = Path(__file__).resolve().parents[3]
if str(_CORE_DIR) not in sys.path:
    sys.path.insert(0, str(_CORE_DIR))

router = APIRouter(prefix="/api/stream", tags=["stream"])
logger = logging.getLogger("coding_os.web.stream")

_TASK_RE = re.compile(r"^TASK-(\d+)")
_HEARTBEAT_INTERVAL = 15.0  # seconds


def _tasks_dir() -> Path:
    """Resolve the docs/tasks directory (project-scoped).

    PURPOSE: Find where TASK-*.md files live for polling.
    INPUT:   none.
    OUTPUT:  Path to docs/tasks/.
    DEPENDENCIES: core.web._project_context.current_project_root.
    """
    from web._project_context import current_project_root

    return current_project_root() / "docs" / "tasks"


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


def _db_conn() -> sqlite3.Connection:
    """Open project SQLite DB used by board/task routes."""
    from web._project_context import current_db_path

    return sqlite3.connect(str(current_db_path()), check_same_thread=False)


def _latest_transition(conn: sqlite3.Connection, task_id: str) -> dict[str, object | None]:
    """Return latest status transition row for a task."""
    row = conn.execute(
        """
        SELECT old_status, new_status, agent_session, transitioned_at
        FROM task_status_history
        WHERE task_id = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (task_id,),
    ).fetchone()
    if not row:
        return {"old_status": None, "new_status": None, "agent_session": None, "transitioned_at": None}
    return {
        "old_status": row[0],
        "new_status": row[1],
        "agent_session": row[2],
        "transitioned_at": row[3],
    }


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


_TRANSITION_ALIGN_SECS = 8  # file mtime within this many seconds of a DB row = same event


async def _event_generator() -> AsyncGenerator[str, None]:
    """Poll docs/tasks/ and yield SSE events.

    PURPOSE: Core SSE generator — monitors task files and emits change events.
    INPUT:   none (uses module-level constants).
    OUTPUT:  Async generator of SSE event strings.
    DEPENDENCIES: asyncio, pathlib.
    NOTES:   Emits canonical DB transitions FIRST each cycle, then
             promotes raw file edits to human-authored events, suppressing
             duplicates by aligning mtime with the transition timestamp.
             Heartbeat every 15s keeps idle connections alive.
    """
    tasks_dir = _tasks_dir()
    poll = _poll_interval_secs()
    last_mtimes: dict[str, float] = {}
    last_history_id = 0
    last_heartbeat = time.monotonic()

    try:
        conn = _db_conn()
        try:
            row = conn.execute("SELECT COALESCE(MAX(id), 0) FROM task_status_history").fetchone()
            last_history_id = int(row[0]) if row and row[0] is not None else 0
        finally:
            conn.close()
    except sqlite3.Error:
        last_history_id = 0

    yield await _sse_event("connected", {"message": "SSE stream connected", "poll_ms": int(poll * 1000)})

    while True:
        await asyncio.sleep(poll)

        now = time.monotonic()
        if now - last_heartbeat >= _HEARTBEAT_INTERVAL:
            yield await _sse_event("heartbeat", {"ts": int(time.time())})
            last_heartbeat = now

        # ----- Canonical DB transitions (authoritative; emitted first) -----
        try:
            conn = _db_conn()
            try:
                rows = conn.execute(
                    """
                    SELECT h.id, h.task_id, h.old_status, h.new_status,
                           h.agent_session, h.transitioned_at, h.reason,
                           t.status
                    FROM task_status_history h
                    LEFT JOIN tasks t ON t.task_id = h.task_id
                    WHERE h.id > ?
                    ORDER BY h.id ASC
                    LIMIT 200
                    """,
                    (last_history_id,),
                ).fetchall()
            finally:
                conn.close()
        except sqlite3.Error as exc:
            logger.debug("stream history fetch failed: %s", exc)
            rows = []

        emitted_recent: dict[str, float] = {}  # task_id -> transitioned_at
        for r in rows:
            row_id = int(r[0])
            last_history_id = max(last_history_id, row_id)
            task_id = r[1]
            ts = float(r[5]) if r[5] is not None else float(time.time())
            emitted_recent[task_id] = ts
            yield await _sse_event(
                "task-updated",
                {
                    "task_id": task_id,
                    # Normalise '' → null for creation rows (see history
                    # endpoint for the full rationale).
                    "old_status": r[2] if r[2] else None,
                    "new_status": r[3],
                    "status": r[3],
                    "agent_session": r[4],
                    "reason": r[6],
                    "ts": int(ts),
                    "source": "db",
                    # t.status at the moment this event is emitted — helps
                    # the UI show "→ NOW: complete" when the transition is
                    # historical and the task has moved on.
                    "current_status": r[7],
                },
            )

        # ----- File-watch promotion (human edits not backed by a DB row) ---
        if not tasks_dir.exists():
            tasks = []
        else:
            tasks = list(tasks_dir.glob("TASK-*.md"))

        for md_file in tasks:
            try:
                mtime = md_file.stat().st_mtime
            except OSError:
                continue

            fname = md_file.name
            prev_mtime = last_mtimes.get(fname)

            if prev_mtime is None:
                last_mtimes[fname] = mtime
                continue
            if mtime == prev_mtime:
                continue

            last_mtimes[fname] = mtime
            m = _TASK_RE.match(fname)
            task_id = f"TASK-{m.group(1)}" if m else fname.replace(".md", "")

            # If we just emitted a DB event for this task close to the
            # file mtime, the file change is the same event — skip.
            recent_ts = emitted_recent.get(task_id)
            if recent_ts is not None and abs(mtime - recent_ts) <= _TRANSITION_ALIGN_SECS:
                continue

            meta = _read_task_meta(md_file)
            # A file edit without an accompanying DB transition is a raw
            # human edit — frontmatter agent_session would be the LAST
            # author (stale), so treat it as human (null).
            yield await _sse_event(
                "task-updated",
                {
                    "task_id": task_id,
                    "old_status": None,
                    "new_status": meta["status"],
                    "status": meta["status"],
                    "agent_session": None,
                    "reason": "file edit",
                    "ts": int(time.time()),
                    "source": "file",
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
    # Use plain SSE framing to keep event names stable (`task-updated`) across
    # environments and avoid adapter-specific formatting differences.
    from fastapi.responses import StreamingResponse

    async def _plain_gen():
        async for chunk in _event_generator():
            yield chunk.encode("utf-8")

    return StreamingResponse(
        _plain_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/history")
async def stream_history(
    limit: int = Query(20),
    _rl=Depends(make_rate_limit_dep("stream.history")),
    _m=Depends(make_metrics_dep("stream.history")),
):
    """Recent official status transitions for stream bootstrap."""
    limit = max(1, min(200, int(limit)))
    conn = _db_conn()
    try:
        # LEFT JOIN so we can annotate every historical row with the
        # task's CURRENT status.  Without this the UI shows "ready ->
        # in_progress" for a task that has since moved on to complete,
        # and the board column is (correctly) empty — a confusing mismatch.
        rows = conn.execute(
            """
            SELECT
                h.task_id,
                h.old_status,
                h.new_status,
                h.agent_session,
                h.reason,
                h.transitioned_at,
                t.status AS current_status
            FROM task_status_history h
            LEFT JOIN tasks t ON t.task_id = h.task_id
            ORDER BY h.transitioned_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    except sqlite3.Error as exc:
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "category": "unavailable",
                    "retryable": False,
                    "message": f"stream history unavailable: {exc}",
                },
            },
        )
    finally:
        conn.close()

    # cos_task_create writes old_status='' for creation rows because the
    # task_status_history.old_status column is NOT NULL. Normalise back
    # to null on the wire so the UI's `isCreate = !old_status` check sees
    # a canonical sentinel and doesn't need to special-case "".
    events = [
        {
            "task_id": r[0],
            "old_status": r[1] if r[1] else None,
            "new_status": r[2],
            "agent_session": r[3],
            "reason": r[4],
            "transitioned_at": r[5],
            "current_status": r[6],
        }
        for r in rows
    ]
    return {
        "data": {
            "events": events,
            "count": len(events),
        },
        "meta": {
            "layer": "stream",
            "source": "task_status_history",
            "limit": limit,
        },
    }
