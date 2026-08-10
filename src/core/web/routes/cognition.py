"""core.web.routes.cognition — /api/cognition/* HTTP wrappers."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import sys
import time
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from .._deps import make_metrics_dep, make_rate_limit_dep
from .._envelope import ENVELOPE_ERROR_RESPONSES, unwrap
from ._bounded_read import DEFAULT_WINDOW, tail_lines

# A trace jsonl can reach GBs (e.g. a long run_await loop). Read only the tail
# so the viewer shows the most-recent events without OOMing the server. TASK-225.
_MAX_TRACE_EVENTS = 2000

logger = logging.getLogger(__name__)

_CORE_DIR = Path(__file__).resolve().parents[3]
if str(_CORE_DIR) not in sys.path:
    sys.path.insert(0, str(_CORE_DIR))

router = APIRouter(prefix="/api/cognition", tags=["cognition"], responses=ENVELOPE_ERROR_RESPONSES)


def _state_dir() -> Path:
    """Resolve the .coding-os state directory.

    Per-project requests (`/api/p/<slug>/...`) ALWAYS use that project's
    `.coding-os/` — env vars cannot override scope. Otherwise env vars
    win for backwards compatibility with tests + manual overrides.
    """
    from web._project_context import current_project_root, is_explicit_project_scope

    if is_explicit_project_scope():
        return current_project_root() / ".coding-os"
    base = os.environ.get("COS_STATE_DIR") or os.environ.get("COS_AGENT_DIR")
    if base:
        return Path(base).resolve()
    return current_project_root() / ".coding-os"


def _cognition_module():
    """Lazy import for cognition tools."""
    try:
        tos_dir = _CORE_DIR / "thinking_os"
        if str(tos_dir) not in sys.path:
            sys.path.insert(0, str(tos_dir))
        from tools import cognition as _cog  # type: ignore

        return _cog
    except ImportError:
        return None


def _unavailable(msg: str = "cognition tools not available"):
    return json.dumps(
        {
            "ok": False,
            "error": {"category": "unavailable", "retryable": False, "message": msg},
        }
    )


def _auto_route_model(prompt: str) -> dict:
    """Deterministic Auto-model triage (hub-architecture.md § Hub settings
    contract): classify the prompt, prefer cos_route_model's empirical pick
    when history exists, else the settings' orchestrator_model."""
    from .settings import _load as _load_hub_settings

    routing_cfg = _load_hub_settings().get("model_routing") or {}
    if not routing_cfg.get("enabled"):
        return {"error": "model 'auto' requires settings.model_routing.enabled"}

    cog = _cognition_module()
    complexity = "COMPLICATED"
    if cog is not None and hasattr(cog, "classify_prompt_heuristic"):
        complexity = cog.classify_prompt_heuristic(prompt)["complexity"]

    routed = ""
    source = "orchestrator_default"
    try:
        from tools.routing import route_model  # type: ignore

        from thinking_os.database import resolve_db_path  # type: ignore

        conn = sqlite3.connect(str(resolve_db_path()))
        try:
            recommendation = route_model(conn, complexity=complexity)
        finally:
            conn.close()
        if int(recommendation.get("data_points") or 0) > 0:
            routed = str(recommendation.get("recommended_model") or "")
            source = "empirical"
    except Exception as exc:
        logger.debug("auto-route empirical lookup failed: %s", exc)

    if not routed:
        routed = str(routing_cfg.get("orchestrator_model") or "")
        source = "orchestrator_default"
    return {"model": routed, "complexity": complexity, "source": source}


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
    # A path segment (session_id / agent) is safe iff it is a non-empty run of
    # [A-Za-z0-9_-] — rejects '/', '..', and any traversal before it reaches a
    # filesystem join. Session ids are ses-<agent>-<ts>-<pid>; agents are alnum.
    return bool(seg) and all(c.isalnum() or c in "-_" for c in seg)


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
            yield f"event: error\ndata: {json.dumps({'message': str(exc)})}\n\n".encode()

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


def _db_path() -> str | None:
    """Resolve coding-os SQLite DB path via canonical helper.

    Returns None when nothing exists yet (the route returns a typed
    ``unavailable`` envelope in that case).
    """
    try:
        from thinking_os.database import resolve_db_path  # type: ignore
        from web._project_context import current_project_root  # type: ignore[import]

        path = resolve_db_path(current_project_root())
        if path.exists():
            return str(path)
    except Exception as exc:
        logger.debug("project-root db path resolve failed: %s", exc)
    return None


@router.get("/cost")
def dispatcher_cost_summary(
    formula_id: str | None = Query(None, description="Filter to one formula"),
    limit: int = Query(50, ge=1, le=500),
    _rl=Depends(make_rate_limit_dep("cognition.cost")),
    _m=Depends(make_metrics_dep("cognition.cost")),
):
    """Aggregate dispatch cost rolled up by formula and day (T2.4)."""
    db = _db_path()
    if db is None:
        return unwrap(
            json.dumps(
                {
                    "ok": True,
                    "data": {
                        "rows": [],
                        "total_usd": 0.0,
                        "count": 0,
                        "meta": {"layer": "cognition"},
                    },
                }
            )
        )

    try:
        params: list = []
        where = "WHERE cost_usd IS NOT NULL"
        if formula_id:
            where += " AND formula_id = ?"
            params.append(formula_id)
        query_sql = (
            f"SELECT formula_id, date(ts) as day, "
            f"SUM(cost_usd) as total_cost_usd, COUNT(*) as count, "
            f"AVG(latency_ms) as avg_latency_ms "
            f"FROM formula_dispatches {where} "
            f"GROUP BY formula_id, day "
            f"ORDER BY day DESC, total_cost_usd DESC "
            f"LIMIT ?"
        )
        params.append(limit)
        with sqlite3.connect(db) as conn:
            conn.row_factory = sqlite3.Row
            rows = [dict(r) for r in conn.execute(query_sql, params).fetchall()]
            total_usd = sum(r["total_cost_usd"] or 0 for r in rows)
    except Exception as exc:
        return unwrap(
            json.dumps(
                {
                    "ok": False,
                    "error": {"category": "internal", "retryable": False, "message": str(exc)},
                }
            )
        )

    return unwrap(
        json.dumps(
            {
                "ok": True,
                "data": {
                    "rows": rows,
                    "total_usd": round(total_usd, 6),
                    "count": len(rows),
                    "meta": {"layer": "cognition"},
                },
            }
        )
    )


@router.get("/cost/health")
def dispatcher_cost_health(
    _rl=Depends(make_rate_limit_dep("cognition.cost_health")),
    _m=Depends(make_metrics_dep("cognition.cost_health")),
):
    """Cost-health gauges over formula_dispatches: MAD anomaly, burn-rate, budget ladder."""
    empty = {
        "anomaly": {"ok": True, "n": 0, "outliers": []},
        "burn": {"days": 0},
        "budget": {"level": "ok", "cap_usd": None, "spent_usd": 0.0, "allowed": True},
        "overall_ok": True,
        "meta": {"layer": "cognition"},
    }
    db = _db_path()
    if db is None:
        return unwrap(json.dumps({"ok": True, "data": empty}))
    try:
        from thinking_os import budget

        anomaly = budget.cost_anomaly(db)
        burn = budget.cost_burn_rate(db)
        gate = budget.check(db)
        data = {
            "anomaly": anomaly,
            "burn": burn,
            "budget": {
                "level": gate.level,
                "cap_usd": gate.cap_usd,
                "spent_usd": round(gate.spent_usd, 6),
                "allowed": gate.allowed,
            },
            "overall_ok": bool(anomaly.get("ok", True) and gate.level != "hard_stop"),
            "meta": {"layer": "cognition"},
        }
        return unwrap(json.dumps({"ok": True, "data": data}))
    except Exception as exc:
        logger.debug("cost/health failed, failing open: %s", exc)
        return unwrap(json.dumps({"ok": True, "data": empty}))


@router.get("/dispatchers")
def list_dispatchers(
    limit: int = Query(100, ge=1, le=1000),
    status: str | None = Query(None),
    _rl=Depends(make_rate_limit_dep("cognition.dispatchers")),
    _m=Depends(make_metrics_dep("cognition.dispatchers")),
):
    """List recent formula dispatches with telemetry (T19.1)."""
    db = _db_path()
    if db is None:
        return unwrap(
            json.dumps(
                {
                    "ok": True,
                    "data": {"dispatches": [], "count": 0, "meta": {"layer": "cognition"}},
                }
            )
        )

    try:
        params: list = []
        where = "WHERE cost_usd IS NOT NULL"
        if status:
            where += " AND status = ?"
            params.append(status)
        params.append(limit)
        with sqlite3.connect(db) as conn:
            conn.row_factory = sqlite3.Row
            rows = [
                dict(r)
                for r in conn.execute(
                    f"SELECT session_id, formula_id, ts, cost_usd, budget_usd, "
                    f"status, latency_ms "
                    f"FROM formula_dispatches {where} "
                    f"ORDER BY ts DESC LIMIT ?",
                    params,
                ).fetchall()
            ]
    except Exception as exc:
        return unwrap(
            json.dumps(
                {
                    "ok": False,
                    "error": {"category": "internal", "retryable": False, "message": str(exc)},
                }
            )
        )

    return unwrap(
        json.dumps(
            {
                "ok": True,
                "data": {"dispatches": rows, "count": len(rows), "meta": {"layer": "cognition"}},
            }
        )
    )


@router.get("/dispatchers/{session_id}/tools")
def dispatcher_tools(
    session_id: str,
    _rl=Depends(make_rate_limit_dep("cognition.dispatcher_tools")),
    _m=Depends(make_metrics_dep("cognition.dispatcher_tools")),
):
    """Parse tool_calls_jsonb for one dispatch session (T19.2)."""
    db = _db_path()
    if db is None:
        raise HTTPException(status_code=503, detail="DB not available")

    try:
        with sqlite3.connect(db) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT tool_calls_jsonb, tool_failures_jsonb "
                "FROM formula_dispatches WHERE session_id = ? "
                "ORDER BY ts DESC LIMIT 1",
                (session_id,),
            ).fetchone()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if row is None:
        raise HTTPException(status_code=404, detail=f"session {session_id!r} not found")

    def _parse(col: str | None) -> list:
        if not col:
            return []
        try:
            parsed = json.loads(col)
            return parsed if isinstance(parsed, list) else []
        except (json.JSONDecodeError, TypeError):
            return []

    tool_calls = _parse(row["tool_calls_jsonb"])
    failures = _parse(row["tool_failures_jsonb"])
    return unwrap(
        json.dumps(
            {
                "ok": True,
                "data": {
                    "session_id": session_id,
                    "tool_calls": tool_calls,
                    "failures": failures,
                    "count": len(tool_calls),
                    "meta": {"layer": "cognition"},
                },
            }
        )
    )


@router.get("/analyze")
def cognition_analyze(
    task_description: str = Query(...),
    complexity_hint: str | None = Query(None),
    _rl=Depends(make_rate_limit_dep("cognition.analyze")),
    _m=Depends(make_metrics_dep("cognition.analyze")),
):
    """Analyze a task via cos_analyze_task."""
    cog = _cognition_module()
    if cog is None:
        return unwrap(_unavailable())
    # The cognition module exposes analyze_task directly (not through MCP wrapper).
    try:
        if hasattr(cog, "analyze_task"):
            result = cog.analyze_task(task_description, complexity_hint=complexity_hint)
            return unwrap(result if isinstance(result, str) else json.dumps(result))
    except Exception as exc:
        return unwrap(
            json.dumps(
                {
                    "ok": False,
                    "error": {"category": "internal", "retryable": False, "message": str(exc)},
                }
            )
        )
    return unwrap(_unavailable("analyze_task not available in this cognition module version"))


# ---------------------------------------------------------------------------
# Chat surface — Claude Agent SDK transcript browser + resume (TASK-chat)
# ---------------------------------------------------------------------------


_ADAPTER_DISPATCHER_MOD = None
_ADAPTER_DISPATCHER_TRIED = False


_CHAT_PRESENCE_WRITER = None
_CHAT_PRESENCE_TRIED = False


# SDK content-block dataclasses don't carry a `type` discriminator


# ---------------------------------------------------------------------------
# Onboarding — docs-scoped session (TASK-246)


# Import-for-side-effect: the chat and onboarding routes decorate the same
# `router` above, so importing this module still registers every /api/cognition
# path exactly as it did before the 2026-08-10 split.
from . import (
    cognition_chat,  # noqa: F401
    cognition_onboarding,  # noqa: F401
)
