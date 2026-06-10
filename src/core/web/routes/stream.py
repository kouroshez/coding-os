"""core.web.routes.stream — /api/stream/events SSE for live board updates."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sqlite3
import sys
import time
from collections.abc import AsyncGenerator
from pathlib import Path

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
    """Resolve the docs/tasks directory (project-scoped)."""
    from web._project_context import current_project_root

    return current_project_root() / "docs" / "tasks"


def _poll_interval_secs() -> float:
    """Read COS_WEB_SSE_POLL_MS from env, default 2000ms."""
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
        return {
            "old_status": None,
            "new_status": None,
            "agent_session": None,
            "transitioned_at": None,
        }
    return {
        "old_status": row[0],
        "new_status": row[1],
        "agent_session": row[2],
        "transitioned_at": row[3],
    }


def _read_task_meta(path: Path) -> dict[str, str | None]:
    """Read the status and agent_session fields from a TASK-*.md frontmatter."""
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
        m_status = re.search(r"^status:\s*(\S+)", content, re.MULTILINE)
        m_agent = re.search(r"^agent_session:\s*(\S+)", content, re.MULTILINE)
        return {
            "status": m_status.group(1).strip("\"'") if m_status else None,
            "agent_session": m_agent.group(1).strip("\"'") if m_agent else None,
        }
    except Exception:
        return {"status": None, "agent_session": None}


async def _sse_event(event_type: str, data: dict) -> str:
    """Format a single SSE event string."""
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


_TRANSITION_ALIGN_SECS = 8  # file mtime within this many seconds of a DB row = same event


def _snapshot_activity() -> dict[str, dict[str, int | str | None]]:
    """{agent: {ts, kind, sid}} where ts = max(last_tool_at, last_prompt_at).

    Drives the agent-activity SSE event so the stream panel surfaces
    tool/prompt fires, not just task transitions.  Returns empty on
    import failure — agents lacking presence files are simply absent.
    """
    try:
        from board_os.hub_adapter_manifest import list_agent_manifest_rows  # type: ignore
        from web.routes.board import _presence_files  # type: ignore
    except ImportError as exc:
        logger.debug("activity import failed: %s", exc)
        return {}
    out: dict[str, dict[str, int | str | None]] = {}
    for r in list_agent_manifest_rows():
        agent = str(r.get("id") or "")
        if not agent:
            continue
        best_ts = 0
        best_kind: str | None = None
        best_sid: str | None = None
        for path in _presence_files(agent):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if data.get("ended_at") is not None:
                continue
            for kind, key in (("tool", "last_tool_at"), ("prompt", "last_prompt_at")):
                ts = data.get(key)
                if isinstance(ts, int) and ts > best_ts:
                    best_ts = ts
                    best_kind = kind
                    best_sid = data.get("session_id") or path.stem
        if best_ts:
            out[agent] = {"ts": best_ts, "kind": best_kind, "sid": best_sid}
    return out


def _snapshot_presence() -> dict[str, str]:
    """Return {agent_id: state} snapshot — drives presence-updated SSE diff.

    Imported lazily because board.py mounts later in the app graph and a
    top-level import would create a cycle on cold reload.
    """
    try:
        from board_os.hub_adapter_manifest import list_agent_manifest_rows  # type: ignore
        from web.routes.board import _presence_state  # type: ignore
    except ImportError as exc:
        logger.debug("presence import failed: %s", exc)
        return {}
    snap: dict[str, str] = {}
    for r in list_agent_manifest_rows():
        agent = str(r.get("id") or "")
        if not agent:
            continue
        try:
            snap[agent] = _presence_state(agent)
        except Exception as exc:
            logger.debug("presence snapshot failed for %s: %s", agent, exc)
    return snap


class _StreamState:
    """Per-connection poll watermarks, mutated only inside _poll_tick."""

    def __init__(self) -> None:
        self.tasks_dir = _tasks_dir()
        self.last_mtimes: dict[str, float] = {}
        self.last_history_id = 0
        self.last_dispatch_id = 0  # T8.6: track formula_dispatches.id watermark
        self.last_presence: dict[str, str] = {}
        self.last_activity: dict[str, dict[str, int | str | None]] = {}


def _init_stream_state() -> _StreamState:
    state = _StreamState()
    state.last_presence = _snapshot_presence()
    state.last_activity = _snapshot_activity()
    try:
        conn = _db_conn()
        try:
            row = conn.execute("SELECT COALESCE(MAX(id), 0) FROM task_status_history").fetchone()
            state.last_history_id = int(row[0]) if row and row[0] is not None else 0
            row = conn.execute("SELECT COALESCE(MAX(id), 0) FROM formula_dispatches").fetchone()
            state.last_dispatch_id = int(row[0]) if row and row[0] is not None else 0
        finally:
            conn.close()
    except sqlite3.Error:
        state.last_history_id = 0
        state.last_dispatch_id = 0
    return state


def _poll_tick(state: _StreamState) -> list[tuple[str, dict]]:
    """One poll iteration's blocking work (DB + presence + file watch).

    Runs on a worker thread via asyncio.to_thread — a locked SQLite DB or a
    large docs/tasks/ glob must never stall the shared uvicorn event loop
    (hub-architecture.md § Concurrency model).
    """
    events: list[tuple[str, dict]] = []

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
                (state.last_history_id,),
            ).fetchall()
        finally:
            conn.close()
    except sqlite3.Error as exc:
        logger.debug("stream history fetch failed: %s", exc)
        rows = []

    emitted_recent: dict[str, float] = {}  # task_id -> transitioned_at
    for r in rows:
        row_id = int(r[0])
        state.last_history_id = max(state.last_history_id, row_id)
        task_id = r[1]
        ts = float(r[5]) if r[5] is not None else float(time.time())
        emitted_recent[task_id] = ts
        events.append(
            (
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
        )

    # ----- Presence diff (P1) — push when an agent transitions
    # active/working/present/offline. The board's React Query cache
    # only refetches /api/board/list on `bump`, so without this loop
    # the live-agents pill stays stale until the next task move.
    try:
        cur_presence = _snapshot_presence()
    except Exception as exc:
        logger.debug("presence snapshot raised: %s", exc)
        cur_presence = state.last_presence
    if cur_presence != state.last_presence:
        changes = {
            a: cur_presence.get(a)
            for a in set(cur_presence) | set(state.last_presence)
            if cur_presence.get(a) != state.last_presence.get(a)
        }
        events.append(
            (
                "presence-updated",
                {
                    "states": cur_presence,
                    "changes": changes,
                    "ts": int(time.time()),
                },
            )
        )
        state.last_presence = cur_presence

    # ----- Agent activity (P7) — emit on tool/prompt timestamp
    # advance so the stream panel shows real-time agent fires, not
    # just task transitions.  Per-agent debounce already lives in
    # the timestamp granularity (1s); we additionally suppress
    # repeats where the *kind* and *sid* didn't change AND ts
    # advanced <2 s, which collapses bursty tool chains.
    try:
        cur_activity = _snapshot_activity()
    except Exception as exc:
        logger.debug("activity snapshot raised: %s", exc)
        cur_activity = state.last_activity
    for agent, cur in cur_activity.items():
        prev = state.last_activity.get(agent)
        cur_ts_raw = cur.get("ts")
        prev_ts_raw = prev.get("ts") if prev else 0
        cur_ts = cur_ts_raw if isinstance(cur_ts_raw, int) else 0
        prev_ts = prev_ts_raw if isinstance(prev_ts_raw, int) else 0
        if cur_ts <= prev_ts:
            continue
        if (
            prev is not None
            and prev.get("kind") == cur.get("kind")
            and prev.get("sid") == cur.get("sid")
            and cur_ts - prev_ts < 2
        ):
            continue
        events.append(
            (
                "agent-activity",
                {
                    "agent": agent,
                    "kind": cur.get("kind"),
                    "sid": cur.get("sid"),
                    "ts": cur_ts,
                },
            )
        )
    state.last_activity = cur_activity

    # ----- Dispatch events (T8.6) -----
    try:
        conn = _db_conn()
        try:
            d_rows = conn.execute(
                """
                SELECT id, session_id, formula_id, status, latency_ms,
                       cost_usd, sub_session_id, model, ts
                FROM formula_dispatches
                WHERE id > ?
                ORDER BY id ASC
                LIMIT 100
                """,
                (state.last_dispatch_id,),
            ).fetchall()
        finally:
            conn.close()
    except sqlite3.Error as exc:
        logger.debug("stream dispatch fetch failed: %s", exc)
        d_rows = []

    for d in d_rows:
        state.last_dispatch_id = max(state.last_dispatch_id, int(d[0]))
        events.append(
            (
                "dispatch-completed",
                {
                    "dispatch_id": int(d[0]),
                    "session_id": d[1],
                    "formula_id": d[2],
                    "status": d[3],
                    "latency_ms": d[4],
                    "cost_usd": d[5],
                    "sub_session_id": d[6],
                    "model": d[7],
                    "ts": d[8],
                },
            )
        )

    # ----- File-watch promotion (human edits not backed by a DB row) ---
    if not state.tasks_dir.exists():
        tasks = []
    else:
        tasks = list(state.tasks_dir.glob("TASK-*.md"))

    for md_file in tasks:
        try:
            mtime = md_file.stat().st_mtime
        except OSError:
            continue

        fname = md_file.name
        prev_mtime = state.last_mtimes.get(fname)

        if prev_mtime is None:
            state.last_mtimes[fname] = mtime
            continue
        if mtime == prev_mtime:
            continue

        state.last_mtimes[fname] = mtime
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
        events.append(
            (
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
        )
    return events


async def _event_generator() -> AsyncGenerator[str, None]:
    """Poll docs/tasks/ and yield SSE events (blocking work off-loop)."""
    poll = _poll_interval_secs()
    last_heartbeat = time.monotonic()
    state = await asyncio.to_thread(_init_stream_state)

    yield await _sse_event(
        "connected", {"message": "SSE stream connected", "poll_ms": int(poll * 1000)}
    )

    while True:
        await asyncio.sleep(poll)

        now = time.monotonic()
        if now - last_heartbeat >= _HEARTBEAT_INTERVAL:
            yield await _sse_event("heartbeat", {"ts": int(time.time())})
            last_heartbeat = now

        for event_type, payload in await asyncio.to_thread(_poll_tick, state):
            yield await _sse_event(event_type, payload)


@router.get("/events")
async def sse_events():
    """SSE endpoint for live board task updates."""
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
def stream_history(
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
