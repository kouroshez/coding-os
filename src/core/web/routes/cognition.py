"""core.web.routes.cognition — /api/cognition/* HTTP wrappers.

Module layout:
  _cognition_base           the shared APIRouter + state/db/module accessors
  cognition_dispatch_views  cost, dispatcher roster, tool calls, analyze
  cognition_account_views   provider plan, auth mode and rate-limit windows
  cognition_chat            the Claude Agent SDK transcript browser + resume
  cognition_onboarding      the docs-scoped onboarding session
  this module               the trace list, fetch and SSE stream

The sibling route groups reach the shared accessors through THIS module object
(`from . import cognition as _cog`), so a test that patches `cognition._db_path`
still reaches them. That is why the names below are re-exported rather than
called only where they are defined.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from fastapi import Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from .._deps import make_metrics_dep, make_rate_limit_dep
from .._envelope import unwrap
from ._bounded_read import DEFAULT_WINDOW, safe_segment, tail_lines
from ._cognition_base import (
    _CORE_DIR as _CORE_DIR,
    _MAX_TRACE_EVENTS,
    _auto_route_model as _auto_route_model,
    _cognition_module as _cognition_module,
    _db_path as _db_path,
    _state_dir,
    _unavailable as _unavailable,
    router as router,
)

logger = logging.getLogger(__name__)


def _enrich_trace_row(row: dict) -> dict:
    """Augment a session row with cheap trace stats (event_count, first_kind).

    Every row returns the same shape — frontend `TraceList` indexes
    `mtime_ts`, `event_count`, `first_event_kind` unconditionally; missing
    fields make the rows render with broken relative-time and "0ev"
    placeholders. Session-only entries (no jsonl yet) get derived stats:
      - mtime_ts = newest activity timestamp from the session.json
      - event_count = 0
      - first_event_kind = None
    """
    trace_path = row.get("trace_path")
    enriched = dict(row)
    enriched.setdefault("event_count", 0)
    enriched.setdefault("first_event_kind", None)

    if trace_path:
        p = Path(trace_path)
        event_count = 0
        first_kind: str | None = None
        try:
            with p.open("r", encoding="utf-8", errors="ignore") as fh:
                for i, line in enumerate(fh):
                    stripped = line.strip()
                    if not stripped:
                        continue
                    event_count += 1
                    if first_kind is None:
                        try:
                            payload = json.loads(stripped)
                            first_kind = payload.get("kind") if isinstance(payload, dict) else None
                        except (json.JSONDecodeError, ValueError):
                            first_kind = "raw"
                    if i > 5000:
                        break  # cap — prevent pathological scans
        except OSError as exc:
            logger.debug("trace scan skipped %s: %s", p, exc)
        enriched["path"] = trace_path  # legacy alias kept for older clients
        enriched["event_count"] = event_count
        enriched["first_event_kind"] = first_kind

    # Pick the most-recent timestamp available — same rule as the
    # /api/cognition/traces sort key (max, not first-truthy).
    candidates = [
        row.get("modified_ts"),
        row.get("last_tool_at"),
        row.get("last_prompt_at"),
        row.get("last_stop_at"),
        row.get("started_at"),
    ]
    fresh = max((float(c) for c in candidates if c is not None), default=0.0)
    enriched["mtime_ts"] = int(fresh) if fresh > 0 else None
    return enriched


@router.get("/traces")
def list_traces(
    agent: str | None = Query(None, description="Agent name (e.g. 'claude')"),
    _rl=Depends(make_rate_limit_dep("cognition.traces")),
    _m=Depends(make_metrics_dep("cognition.traces")),
):
    """List trace + session-only entries with activity sort."""
    from web.routes.observability import _scan_sessions  # type: ignore

    state = _state_dir()
    if not state.exists():
        return unwrap(
            json.dumps(
                {
                    "ok": True,
                    "data": {
                        "sessions": [],
                        "count": 0,
                        "trace_count": 0,
                        "session_count": 0,
                        "meta": {"layer": "cognition"},
                    },
                }
            )
        )

    rows = _scan_sessions(state, agent_filter=agent)
    enriched = [_enrich_trace_row(r) for r in rows]
    trace_count = sum(1 for r in enriched if r.get("has_trace"))
    session_count = sum(1 for r in enriched if r.get("source") in ("session-only", "trace+session"))

    return unwrap(
        json.dumps(
            {
                "ok": True,
                "data": {
                    "sessions": enriched,
                    "count": len(enriched),
                    "trace_count": trace_count,
                    "session_count": session_count,
                    "meta": {"layer": "cognition"},
                },
            }
        )
    )


def _safe_seg(seg: str | None) -> bool:
    # Thin alias kept for the call sites below; the rule lives in _bounded_read
    # so cognition, roles, observability and the config routes cannot drift.
    return safe_segment(seg or "")


def _find_trace_file(
    state: Path, session_id: str, agent: str | None
) -> tuple[Path | None, str | None]:
    """Locate a session's jsonl trace file across all (or one) agent dir."""
    if not _safe_seg(session_id) or (agent is not None and not _safe_seg(agent)):
        return (None, None)
    if agent:
        candidate = state / agent / "traces" / f"{session_id}.jsonl"
        return (candidate, agent) if candidate.exists() else (None, agent)
    if not state.is_dir():
        return (None, None)
    for agent_dir in state.iterdir():
        if not agent_dir.is_dir():
            continue
        candidate = agent_dir / "traces" / f"{session_id}.jsonl"
        if candidate.exists():
            return (candidate, agent_dir.name)
    return (None, None)


def _find_session_meta(
    state: Path, session_id: str, agent: str | None
) -> tuple[dict | None, str | None]:
    """Locate a session's .json metadata across all (or one) agent dir."""
    if not _safe_seg(session_id) or (agent is not None and not _safe_seg(agent)):
        return (None, None)
    if agent:
        p = state / agent / "sessions" / f"{session_id}.json"
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8")), agent
            except (OSError, json.JSONDecodeError):
                return None, agent
        return None, agent
    if not state.is_dir():
        return None, None
    for agent_dir in state.iterdir():
        if not agent_dir.is_dir():
            continue
        p = agent_dir / "sessions" / f"{session_id}.json"
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8")), agent_dir.name
            except (OSError, json.JSONDecodeError):
                return None, agent_dir.name
    return None, None


@router.get("/trace/{session_id}")
def get_trace(
    session_id: str,
    agent: str | None = Query(None),
    _rl=Depends(make_rate_limit_dep("cognition.trace")),
    _m=Depends(make_metrics_dep("cognition.trace")),
):
    """Read trace events for a session; fall back to session metadata when no jsonl yet."""
    state = _state_dir()
    target, resolved_agent = _find_trace_file(state, session_id, agent)
    session_meta, meta_agent = _find_session_meta(state, session_id, agent)

    if target is None and session_meta is None:
        raise HTTPException(
            status_code=404,
            detail=f"trace {session_id!r} not found (no jsonl trace, no session.json metadata)",
        )

    events: list[dict] = []
    trace_truncated = False
    if target is not None:
        # Tail-read only the last _MAX_TRACE_EVENTS lines (≤256KB window) so a
        # multi-GB trace cannot OOM the server or the response.
        lines, trace_truncated = tail_lines(target, max_lines=_MAX_TRACE_EVENTS)
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                events.append(json.loads(stripped))
            except json.JSONDecodeError:
                events.append({"raw": stripped})

    return unwrap(
        json.dumps(
            {
                "ok": True,
                "data": {
                    "session_id": session_id,
                    "agent": resolved_agent or meta_agent,
                    "events": events,
                    "count": len(events),
                    "truncated": trace_truncated,
                    "session": session_meta,
                    "has_trace": target is not None,
                    "source": "trace+session"
                    if target and session_meta
                    else ("trace-only" if target else "session-only"),
                    "meta": {"layer": "cognition"},
                },
            }
        )
    )


def _drain_trace_events(log: Path, pos: int) -> tuple[list[dict[str, Any]], int]:
    # Blocking stat + read (run on a worker thread by the SSE loop) — mirrors
    # hooks.stream so a burst of trace lines never stalls the event loop.
    if not log.exists():
        return [], pos
    size = log.stat().st_size
    if size < pos:
        pos = 0  # rotated
    if size <= pos:
        return [], pos
    with log.open("r", encoding="utf-8", errors="ignore") as fh:
        fh.seek(pos)
        chunk = fh.read()
        pos = fh.tell()
    parsed: list[dict[str, Any]] = []
    for line in chunk.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            parsed.append(json.loads(stripped))
        except json.JSONDecodeError:
            parsed.append({"raw": stripped})
    return parsed, pos


def _initial_trace_pos(log: Path, max_bytes: int = DEFAULT_WINDOW) -> int:
    """Byte offset for a bounded initial replay: the start of the first whole
    line within the last `max_bytes`. A long session's trace jsonl can reach
    many MB; replaying it whole on connect would read the entire file into
    memory (the same DoS the bounded-read helper guards for the non-streaming
    reads). Returns 0 when the file fits the window or cannot be stat'd."""
    try:
        size = log.stat().st_size
    except OSError:
        return 0
    if size <= max_bytes:
        return 0
    try:
        with log.open("rb") as fh:
            fh.seek(size - max_bytes)
            fh.readline()  # discard the partial leading line
            return fh.tell()
    except OSError:
        return 0


@router.get("/trace/{session_id}/stream")
async def stream_trace(
    session_id: str,
    agent: str | None = Query(None),
    _rl=Depends(make_rate_limit_dep("cognition.trace_stream")),
    _m=Depends(make_metrics_dep("cognition.trace_stream")),
):
    """SSE: tail (and replay from the start) a session's append-only cognition trace jsonl."""
    if not _safe_seg(session_id) or (agent is not None and not _safe_seg(agent)):
        raise HTTPException(status_code=400, detail="invalid session_id or agent")
    state = _state_dir()
    target, _resolved_agent = _find_trace_file(state, session_id, agent)
    # The dispatch may not have created the file yet — resolve the canonical
    # path so tailing begins the instant the first event lands. Segments are
    # validated above, so this join cannot escape the state dir.
    log = (
        target
        if target is not None
        else state / (agent or "claude") / "traces" / f"{session_id}.jsonl"
    )
    poll_secs = float(os.environ.get("COS_TRACE_STREAM_POLL_MS", "750")) / 1000.0
    heartbeat_secs = 15.0
    idle_terminate_secs = float(os.environ.get("COS_TRACE_STREAM_IDLE_TERMINATE_S", "30"))

    async def gen() -> AsyncGenerator[bytes, None]:
        yield f"event: connected\ndata: {json.dumps({'session_id': session_id})}\n\n".encode()
        # Replay from a bounded tail window so a viewer connecting mid-run sees
        # the recent trace, then keeps tailing new lines. Starting at 0 would
        # read a multi-MB trace whole on connect (worker-memory spike).
        pos = _initial_trace_pos(log)
        last_beat = time.monotonic()
        last_event = time.monotonic()
        saw_completed = False
        try:
            while True:
                events, pos = await asyncio.to_thread(_drain_trace_events, log, pos)
                for evt in events:
                    yield f"event: trace\ndata: {json.dumps(evt, ensure_ascii=False)}\n\n".encode()
                if events:
                    last_event = time.monotonic()
                    if any(
                        isinstance(e, dict) and e.get("kind") == "dispatch_completed"
                        for e in events
                    ):
                        saw_completed = True
                # Self-terminate once a completion has been seen AND the trace has
                # been idle for a grace period. A supervisor session emits one
                # dispatch_completed per role in a chain, so terminating on the
                # FIRST would drop later roles — the idle window ends a lone
                # sub-session promptly while letting a multi-role run keep going.
                elif saw_completed and (time.monotonic() - last_event) > idle_terminate_secs:
                    yield b"event: done\ndata: {}\n\n"
                    return
                if time.monotonic() - last_beat > heartbeat_secs:
                    yield f"event: heartbeat\ndata: {json.dumps({'ts': int(time.time())})}\n\n".encode()
                    last_beat = time.monotonic()
                await asyncio.sleep(poll_secs)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("trace stream failed")
            message = safe_error_message(exc, "cognition stream failed", logger)
            yield f"event: error\ndata: {json.dumps({'message': message})}\n\n".encode()

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ---------------------------------------------------------------------------
# T2.4 / T19.1 — Dispatcher cost panel
# ---------------------------------------------------------------------------


# Import-for-side-effect: the dispatch-view, chat and onboarding routes decorate
# the same `router` above, so importing this module still registers every
# /api/cognition path exactly as it did before the 2026-08-10 split.
from .._envelope import safe_error_message
from . import (
    cognition_account_views,  # noqa: F401
    cognition_chat,  # noqa: F401
    cognition_dispatch_views,  # noqa: F401
    cognition_onboarding,  # noqa: F401
)

# Re-exported so `from core.web.routes.cognition import _safe_serialize` keeps
# resolving — the split moved the bodies, not the public reach.
from ._cognition_serialize import _sse_chunk
from .cognition_account_views import provider_quota as provider_quota
from .cognition_chat import (
    _dispatch_transcript_chat,
    _prime_with_project_description,
    _role_names,
    _role_system_prompt,
    _safe_serialize,
)
from .cognition_dispatch_views import (
    cognition_analyze as cognition_analyze,
    dispatcher_cost_health as dispatcher_cost_health,
    dispatcher_cost_summary as dispatcher_cost_summary,
    dispatcher_tools as dispatcher_tools,
    list_dispatchers as list_dispatchers,
)
from .cognition_onboarding import _onboard_write_allowed, _onboarding_state

__all__ = [
    "_dispatch_transcript_chat",
    "_initial_trace_pos",
    "_onboard_write_allowed",
    "_onboarding_state",
    "_prime_with_project_description",
    "_role_names",
    "_role_system_prompt",
    "_safe_serialize",
    "_sse_chunk",
    "router",
]
