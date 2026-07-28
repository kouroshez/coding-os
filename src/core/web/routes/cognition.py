"""core.web.routes.cognition — /api/cognition/* HTTP wrappers."""

from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
import os
import sqlite3
import sys
import time
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
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
        from thinking_os.database import resolve_db_path  # type: ignore
        from tools.routing import route_model  # type: ignore

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
    log = target if target is not None else state / (agent or "claude") / "traces" / f"{session_id}.jsonl"
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
                    if any(isinstance(e, dict) and e.get("kind") == "dispatch_completed" for e in events):
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


def _claude_sdk():
    """Lazy import the Claude Agent SDK; return None when missing."""
    try:
        import claude_agent_sdk  # type: ignore

        return claude_agent_sdk
    except ImportError as exc:
        logger.debug("claude_agent_sdk unavailable: %s", exc)
        return None


def _project_cwd() -> str:
    from web._project_context import current_project_root

    return str(current_project_root())


_ADAPTER_DISPATCHER_MOD = None
_ADAPTER_DISPATCHER_TRIED = False


def _adapter_dispatcher():
    """Load src/adapters/claude/sdk_dispatcher.py once — the adapter SDK-construction
    seam (P8: every ClaudeAgentOptions build crosses this boundary into the adapter)."""
    global _ADAPTER_DISPATCHER_MOD, _ADAPTER_DISPATCHER_TRIED
    if _ADAPTER_DISPATCHER_TRIED:
        return _ADAPTER_DISPATCHER_MOD
    _ADAPTER_DISPATCHER_TRIED = True
    try:
        import importlib.util
        from pathlib import Path

        path = Path(__file__).resolve().parents[3] / "adapters" / "claude" / "sdk_dispatcher.py"
        spec = importlib.util.spec_from_file_location("cos_adapter_claude_dispatcher", path)
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            _ADAPTER_DISPATCHER_MOD = mod
    except Exception as exc:
        logger.debug("adapter dispatcher load failed: %s", exc)
    return _ADAPTER_DISPATCHER_MOD


def _session_options_builder():
    """The adapter's profile-based session-options builder (SSOT), or None."""
    mod = _adapter_dispatcher()
    return getattr(mod, "claude_session_options", None) if mod else None


def _build_agent_options(**kwargs):
    """Construct ClaudeAgentOptions via the adapter seam — P8: core never builds the
    SDK type itself. Raises if the adapter dispatcher cannot be loaded."""
    mod = _adapter_dispatcher()
    builder = getattr(mod, "claude_agent_options", None) if mod else None
    if builder is None:
        raise RuntimeError("claude adapter ClaudeAgentOptions seam unavailable")
    return builder(**kwargs)


def _chat_session_options(
    profile, *, cwd, model, system_prompt, effort=None, resume=None, fork=False
):
    """Build chat ClaudeAgentOptions via the adapter SSOT builder; on builder error
    fall back to the chat-light kwargs, still constructed through the adapter seam."""
    build = _session_options_builder()
    if build is not None:
        try:
            return build(
                profile,
                cwd=cwd,
                model=model,
                system_prompt=system_prompt,
                effort=effort,
                resume=resume,
                fork=fork,
            )
        except Exception as exc:
            logger.debug("session-options builder call failed (%s); generic seam fallback", exc)
    kwargs = dict(
        cwd=cwd,
        model=model,
        permission_mode="dontAsk",
        setting_sources=[],
        include_partial_messages=True,
        system_prompt=system_prompt,
    )
    if effort:
        kwargs["effort"] = effort
    if profile == "chat_resume":
        if resume:
            kwargs["resume"] = resume
        kwargs["fork_session"] = fork
    return _build_agent_options(**kwargs)


_CHAT_PRESENCE_WRITER = None
_CHAT_PRESENCE_TRIED = False


def _chat_presence_write(cwd: str, sid: str, event: str) -> None:
    """Fire-and-forget Hub-chat presence so the chat shows in the Live-agents HUD (P13)."""
    # Reuse the adapter's unified 12-key writer and stamp the long-lived host
    # pid, so the board's glob reader sees the live chat session (the chat path
    # fires no shell hooks, so nothing else writes its presence).
    global _CHAT_PRESENCE_WRITER, _CHAT_PRESENCE_TRIED
    try:
        if not _CHAT_PRESENCE_TRIED:
            _CHAT_PRESENCE_TRIED = True
            import importlib.util
            from pathlib import Path as _Path

            path = (
                _Path(__file__).resolve().parents[3] / "adapters" / "claude" / "sdk_dispatcher.py"
            )
            spec = importlib.util.spec_from_file_location("cos_adapter_claude_presence", path)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                _CHAT_PRESENCE_WRITER = getattr(mod, "_presence_write", None)
        if _CHAT_PRESENCE_WRITER is not None:
            import os
            from pathlib import Path as _Path

            _CHAT_PRESENCE_WRITER(_Path(cwd), "claude", sid, event, pid=os.getpid())
    except Exception as exc:
        logger.debug("chat presence write skipped (%s): %s", event, exc)


def _serialize_session_info(info: Any) -> dict:
    return {
        "session_id": getattr(info, "session_id", None),
        "summary": getattr(info, "summary", None),
        "custom_title": getattr(info, "custom_title", None),
        "first_prompt": (getattr(info, "first_prompt", None) or "")[:400] or None,
        "last_modified": getattr(info, "last_modified", None),
        "file_size": getattr(info, "file_size", None),
        "git_branch": getattr(info, "git_branch", None),
        "cwd": getattr(info, "cwd", None),
        "tag": getattr(info, "tag", None),
        "created_at": getattr(info, "created_at", None),
    }


def _coerce_block(block: Any) -> dict:
    if not isinstance(block, dict):
        return {"type": "raw", "value": str(block)[:2000]}
    btype = str(block.get("type") or "unknown")
    out: dict = {"type": btype}
    if btype == "text":
        out["text"] = str(block.get("text") or "")
    elif btype == "thinking":
        out["text"] = str(block.get("thinking") or block.get("text") or "")
    elif btype == "tool_use":
        out["id"] = block.get("id")
        out["name"] = block.get("name")
        inp = block.get("input")
        try:
            out["input"] = (
                inp
                if isinstance(inp, (dict, list, str, int, float, bool, type(None)))
                else str(inp)
            )
        except Exception as exc:
            logger.debug("tool_use input coerce fallback: %s", exc)
            out["input"] = str(inp)[:2000]
    elif btype == "tool_result":
        out["tool_use_id"] = block.get("tool_use_id")
        content = block.get("content")
        if isinstance(content, list):
            out["content"] = [
                c.get("text") if isinstance(c, dict) and c.get("type") == "text" else str(c)[:1500]
                for c in content
            ]
        else:
            out["content"] = str(content)[:4000] if content is not None else None
        out["is_error"] = bool(block.get("is_error"))
    elif btype == "image":
        out["source_type"] = (
            block.get("source", {}).get("type") if isinstance(block.get("source"), dict) else None
        )
    else:
        # Catch-all: keep small primitive fields, drop binary noise.
        for k, v in block.items():
            if k == "type":
                continue
            if isinstance(v, (str, int, float, bool, type(None))):
                out[k] = v
    return out


def _serialize_message(msg: Any) -> dict:
    raw = getattr(msg, "message", None)
    if not isinstance(raw, dict):
        raw = {}
    role = raw.get("role") or getattr(msg, "type", None) or "unknown"
    content = raw.get("content")
    blocks: list[dict]
    if isinstance(content, str):
        blocks = [{"type": "text", "text": content}]
    elif isinstance(content, list):
        blocks = [_coerce_block(b) for b in content]
    else:
        blocks = []
    return {
        "uuid": getattr(msg, "uuid", None),
        "session_id": getattr(msg, "session_id", None),
        "type": getattr(msg, "type", None),
        "role": role,
        "model": raw.get("model"),
        "stop_reason": raw.get("stop_reason"),
        "usage": raw.get("usage") if isinstance(raw.get("usage"), dict) else None,
        "blocks": blocks,
        "parent_tool_use_id": getattr(msg, "parent_tool_use_id", None),
    }


@router.get("/chats")
def list_chats(
    limit: int = Query(50, ge=1, le=500),
    _rl=Depends(make_rate_limit_dep("cognition.chats")),
    _m=Depends(make_metrics_dep("cognition.chats")),
):
    """List Claude Agent SDK chat sessions for the current project."""
    sdk = _claude_sdk()
    if sdk is None:
        return unwrap(_unavailable("claude_agent_sdk not installed"))
    try:
        sessions = sdk.list_sessions(directory=_project_cwd(), limit=limit)
    except Exception as exc:
        return unwrap(
            json.dumps(
                {
                    "ok": False,
                    "error": {
                        "category": "internal",
                        "retryable": False,
                        "message": f"list_sessions failed: {exc}",
                    },
                }
            )
        )
    rows = [_serialize_session_info(s) for s in sessions]
    rows.sort(key=lambda r: r.get("last_modified") or 0, reverse=True)
    return unwrap(
        json.dumps(
            {
                "ok": True,
                "data": {
                    "sessions": rows,
                    "count": len(rows),
                    "cwd": _project_cwd(),
                    "meta": {"layer": "cognition", "source": "claude_agent_sdk"},
                },
            }
        )
    )


def _dispatch_transcript_chat(session_id: str) -> dict | None:
    # Fall back to a dispatched sub-session's persisted transcript when the live
    # Claude SDK session no longer exists on disk — resolves the dead sdk_uuid
    # modal link (TASK-667). Keyed on formula_dispatches.sub_session_id (= the
    # SDK session_id the UI links from). Read-only, fail-open.
    db_path = _db_path()
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


@router.get("/chat/{session_id}")
def get_chat(
    session_id: str,
    limit: int = Query(500, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    _rl=Depends(make_rate_limit_dep("cognition.chat_get")),
    _m=Depends(make_metrics_dep("cognition.chat_get")),
):
    """Return a Claude SDK session's metadata + parsed messages."""
    sdk = _claude_sdk()
    if sdk is None:
        return unwrap(_unavailable("claude_agent_sdk not installed"))
    cwd = _project_cwd()
    try:
        info = sdk.get_session_info(session_id, directory=cwd)
    except Exception as exc:
        info = None
        # A user is actively viewing this id — a failure here IS the "session
        # vanished" symptom, so log at warning (captured by logging_os), not debug.
        logger.warning("get_session_info(%s) failed: %s", session_id, exc)
    if info is None:
        fallback = _dispatch_transcript_chat(session_id)
        if fallback is not None:
            return unwrap(json.dumps({"ok": True, "data": fallback}))
        raise HTTPException(status_code=404, detail=f"chat session {session_id!r} not found")
    try:
        messages = sdk.get_session_messages(session_id, directory=cwd, limit=limit, offset=offset)
    except Exception as exc:
        return unwrap(
            json.dumps(
                {
                    "ok": False,
                    "error": {
                        "category": "internal",
                        "retryable": False,
                        "message": f"get_session_messages failed: {exc}",
                    },
                }
            )
        )
    return unwrap(
        json.dumps(
            {
                "ok": True,
                "data": {
                    "session": _serialize_session_info(info),
                    "messages": [_serialize_message(m) for m in messages],
                    "count": len(messages),
                    "offset": offset,
                    "meta": {"layer": "cognition", "source": "claude_agent_sdk"},
                },
            }
        )
    )


# SDK content-block dataclasses don't carry a `type` discriminator
# field — they're disambiguated by Python class.  The frontend renders
# blocks by `b.type === 'text' | 'thinking' | 'tool_use' | …`, so
# without this map every block round-trips as a typeless dict and the
# Cognition / Chats panel shows an empty assistant pill (TASK 2026-05-20
# UI audit).  Names map to the wire-format discriminators that
# ChatView.tsx already understands.
_BLOCK_TYPE_BY_CLASS = {
    "TextBlock": "text",
    "ThinkingBlock": "thinking",
    "ToolUseBlock": "tool_use",
    "ToolResultBlock": "tool_result",
    "ServerToolUseBlock": "server_tool_use",
    "ServerToolResultBlock": "server_tool_result",
}


def _safe_serialize(obj: Any) -> Any:
    """Best-effort recursive serializer for SDK dataclass events."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        cls_name = type(obj).__name__
        # Recurse field-by-field via getattr — NOT dataclasses.asdict, which
        # pre-flattens the whole tree so a nested TextBlock arrives here as a
        # plain dict and never gets its `type` stamped (the streamed
        # AssistantMessage.content[] blocks then lack `type` and the UI drops
        # them → "agent draft shows nothing").
        out: dict[str, Any] = {
            f.name: _safe_serialize(getattr(obj, f.name)) for f in dataclasses.fields(obj)
        }
        block_type = _BLOCK_TYPE_BY_CLASS.get(cls_name)
        if block_type is not None:
            out["type"] = block_type
            # ThinkingBlock stores its text under `.thinking`; the UI
            # reads `.text` for both text + thinking blocks, so mirror
            # the field rather than forking the frontend.
            if block_type == "thinking" and "text" not in out and "thinking" in out:
                out["text"] = out["thinking"]
        return out
    if isinstance(obj, dict):
        return {str(k): _safe_serialize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_safe_serialize(v) for v in obj]
    if isinstance(obj, (str, int, float, bool, type(None))):
        return obj
    return str(obj)[:4000]


def _sse_chunk(event: str, payload: dict) -> bytes:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n".encode()


def _role_system_prompt(role: str | None):
    """Load a role's agent prompt as a claude_code system-prompt append, if valid."""
    import re as _re

    if not role or not _re.match(r"^[a-z_]+$", role):
        return None
    agent_md = Path(__file__).resolve().parents[2] / "thinking_os" / "agents" / f"{role}.md"
    try:
        if agent_md.exists():
            return {
                "type": "preset",
                "preset": "claude_code",
                "append": agent_md.read_text(encoding="utf-8"),
            }
    except OSError:
        pass
    return None


def _role_names(agents_dir: Path) -> list[str]:
    import re as _re

    try:
        return sorted(
            p.stem
            for p in agents_dir.glob("*.md")
            if _re.match(r"^[a-z_]+$", p.stem) and not p.stem.startswith("_")
        )
    except OSError as exc:
        logger.debug("roles scan skipped %s: %s", agents_dir, exc)
        return []


@router.get("/roles")
def list_roles(
    _rl=Depends(make_rate_limit_dep("cognition.roles")),
    _m=Depends(make_metrics_dep("cognition.roles")),
):
    """List the semantic roles a chat session can adopt (producer: thinking_os/agents/*.md)."""
    roles = _role_names(Path(__file__).resolve().parents[2] / "thinking_os" / "agents")
    return unwrap(
        json.dumps(
            {
                "ok": True,
                "data": {"roles": roles, "count": len(roles), "meta": {"layer": "cognition"}},
            }
        )
    )


@router.post("/chat")
async def chat_new(
    body: dict = Body(...),
    _rl=Depends(make_rate_limit_dep("cognition.chat_new")),
    _m=Depends(make_metrics_dep("cognition.chat_new")),
):
    """Start a FRESH Claude session from a prompt (no resume); stream SSE.

    Body: ``{"prompt": str, "model": str|null, "role": str|null}``. Emits a
    ``session`` event carrying the SDK-resolved session id so the UI can open
    the chat under the id that get_session_info / list_sessions actually use.
    Claude-only — returns an ``unavailable`` envelope without the SDK.
    """
    prompt = str(body.get("prompt") or "").strip()
    if not prompt:
        return unwrap(
            json.dumps(
                {
                    "ok": False,
                    "error": {
                        "category": "validation",
                        "retryable": False,
                        "message": "prompt must be non-empty",
                    },
                }
            )
        )
    sdk = _claude_sdk()
    if sdk is None:
        return unwrap(_unavailable("claude_agent_sdk not installed"))

    import secrets
    import time as _time

    model = body.get("model") or None
    routing_decision: dict | None = None
    if model == "auto":
        routing_decision = _auto_route_model(prompt)
        if "error" in routing_decision:
            return unwrap(
                json.dumps(
                    {
                        "ok": False,
                        "error": {
                            "category": "validation",
                            "retryable": False,
                            "message": routing_decision["error"],
                        },
                    }
                )
            )
        model = routing_decision["model"] or None
    role = (str(body.get("role") or "")).strip() or None
    effort = (str(body.get("effort") or "")).strip() or None
    if effort not in (None, "low", "medium", "high", "xhigh", "max"):
        effort = None  # ignore unknown levels rather than failing the turn
    cwd = _project_cwd()
    system_prompt = _role_system_prompt(role) or _chat_system_prompt(model)
    system_prompt = _prime_with_project_description(system_prompt, cwd)
    new_session_id = f"ses-claude-ui-{int(_time.time())}-{secrets.token_hex(3)}"
    # SSOT builder (chat profile): setting_sources=[] (no ~40s SessionStart
    # suite) + programmatic coding-os MCP (cos_* capability) + base-tool
    # allow-list (no Write/Edit → chat can't mutate code) + destructive-Bash
    # deny floor. No session_id: the CLI rejects non-UUID ids; the SDK mints
    # its own UUID, surfaced below from the stream as the `session` event.
    options = _chat_session_options(
        "chat", cwd=cwd, model=model, system_prompt=system_prompt, effort=effort
    )

    async def event_gen():
        yield _sse_chunk(
            "started",
            {"session_id": new_session_id, "prompt": prompt[:200], "model": model, "role": role},
        )
        if routing_decision is not None:
            yield _sse_chunk("routing", routing_decision)
        # The Claude SDK rekeys the minted ses-claude-ui-* id to its OWN
        # transcript uuid, so the minted id 404s on get_session_info and never
        # appears in list_sessions. Emit the SDK-resolved id the moment the
        # stream reveals it (SDK messages carry .session_id) so the UI opens /
        # lists the chat under the id that actually resolves.
        resolved_id = new_session_id
        emitted_session = False
        try:
            async for event in sdk.query(prompt=prompt, options=options):
                if not emitted_session:
                    real_id = getattr(event, "session_id", None)
                    if real_id:
                        resolved_id = str(real_id)
                        logger.info(
                            "chat_new resolved session id=%s (minted=%s)",
                            resolved_id,
                            new_session_id,
                        )
                        yield _sse_chunk("session", {"session_id": resolved_id})
                        emitted_session = True
                        _chat_presence_write(cwd, resolved_id, "prompt")
                kind = type(event).__name__.lower().replace("message", "") or "event"
                yield _sse_chunk(kind, _safe_serialize(event))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("chat_new stream failed")
            yield _sse_chunk("error", {"message": str(exc)})
        if not emitted_session:
            # No event ever carried a session_id — the turn produced no resolvable
            # session. Emitting the minted ses-claude-ui-* id strands the UI on an
            # id that 404s on get_chat (the "session vanished" report), so log it
            # loudly. The fallback id keeps the UI from hanging with no handle.
            logger.warning(
                "chat_new: stream produced no SDK session_id (minted=%s) — UI will 404 on this id",
                new_session_id,
            )
            yield _sse_chunk("session", {"session_id": resolved_id})
        _chat_presence_write(cwd, resolved_id, "stop")
        yield _sse_chunk("done", {"session_id": resolved_id})

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


_CHAT_SYSTEM = (
    "You are the coding-os Hub chat assistant — a direct, helpful conversational "
    "agent for this project. Answer the user's message conversationally in Markdown. "
    "Do NOT prepend the transparency banner (the line starting with the bell emoji) "
    "and skip any cognitive-state / gate / work-log ceremony — that protocol is for "
    "terminal sessions, not Hub chat; just answer. You MAY use the cos_* tools "
    "(memory, graph, docs, board) to ground an answer when it genuinely helps, but "
    "keep replies focused and readable rather than running a full work protocol. "
    "When you commit code for a specific task, include its id like `(TASK-NNN)` in "
    "the commit subject so the board links the commit to that task."
)


def _prime_with_project_description(system_prompt: dict, cwd: str) -> dict:
    """Append the onboarding intake (docs/_meta/project-description.md) to the
    chat system prompt so the first session knows what the project IS (TASK-364).
    Fail-open: missing/unreadable intake leaves the prompt untouched."""
    try:
        intake = Path(cwd) / "docs" / "_meta" / "project-description.md"
        if not intake.is_file():
            return system_prompt
        text = intake.read_text(encoding="utf-8").strip()[:2000]
        if not text or not isinstance(system_prompt, dict) or "append" not in system_prompt:
            return system_prompt
        return {
            **system_prompt,
            "append": system_prompt["append"]
            + "\n\n## Project context (onboarding intake)\n"
            + text,
        }
    except OSError:
        return system_prompt


def _chat_system_prompt(model: str | None) -> dict:
    """claude_code preset + the chat framing, pinning the model name when known."""
    append = _CHAT_SYSTEM
    if model:
        append = (
            f"{_CHAT_SYSTEM}\n\nYou are answering as the `{model}` model. If the user "
            f"asks which model you are, tell them exactly `{model}`."
        )
    return {"type": "preset", "preset": "claude_code", "append": append}


_TASK_AUTHOR_SYSTEM = (
    "You are a task-authoring agent for coding-os. Using ONLY cos_* tools, "
    "research the codebase (cos_graph_query/context, cos_doc_search, "
    "cos_task_search/board) and then create EXACTLY ONE well-formed Scrumban "
    "task with cos_task_create: choose the correct swimlane and kind, write a "
    "one-sentence Outcome and a Given/When/Then Acceptance, and list 1-4 Read "
    "First files. Reconcile against the existing board first and reuse a task "
    "instead of duplicating when appropriate. Do NOT write or edit any code or "
    "files. After creating or identifying the task, state its id and stop."
)


@router.post("/author-task")
async def author_task(
    body: dict = Body(...),
    _rl=Depends(make_rate_limit_dep("cognition.author_task")),
    _m=Depends(make_metrics_dep("cognition.author_task")),
):
    """Headless research+author session that creates one task via cos_task_create. Claude-only."""
    prompt = str(body.get("prompt") or "").strip()
    if not prompt:
        return unwrap(
            json.dumps(
                {
                    "ok": False,
                    "error": {
                        "category": "validation",
                        "retryable": False,
                        "message": "prompt must be non-empty",
                    },
                }
            )
        )
    sdk = _claude_sdk()
    if sdk is None:
        return unwrap(_unavailable("claude_agent_sdk not installed"))

    import secrets
    import time as _time

    model = body.get("model") or None
    cwd = _project_cwd()
    sid = f"ses-claude-author-{int(_time.time())}-{secrets.token_hex(3)}"
    options = _build_agent_options(
        cwd=cwd,
        model=model,
        permission_mode="dontAsk",
        setting_sources=["project"],
        # No session_id — claude CLI requires a UUID; SDK mints its own (emitted below).
        # cos_* only — no Write/Edit/Bash, so it can research + author but never touch code.
        allowed_tools=["mcp__coding-os__*"],
        disallowed_tools=["Write", "Edit", "MultiEdit", "Bash"],
        system_prompt={"type": "preset", "preset": "claude_code", "append": _TASK_AUTHOR_SYSTEM},
        max_turns=30,
    )

    async def event_gen():
        yield _sse_chunk("started", {"session_id": sid, "prompt": prompt[:200], "model": model})
        resolved_id = sid
        emitted_session = False
        try:
            async for event in sdk.query(prompt=prompt, options=options):
                if not emitted_session:
                    real_id = getattr(event, "session_id", None)
                    if real_id:
                        resolved_id = str(real_id)
                        yield _sse_chunk("session", {"session_id": resolved_id})
                        emitted_session = True
                kind = type(event).__name__.lower().replace("message", "") or "event"
                yield _sse_chunk(kind, _safe_serialize(event))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("author_task stream failed")
            yield _sse_chunk("error", {"message": str(exc)})
        if not emitted_session:
            yield _sse_chunk("session", {"session_id": resolved_id})
        yield _sse_chunk("done", {"session_id": resolved_id})

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ---------------------------------------------------------------------------
# Onboarding — docs-scoped session (TASK-246)
# ---------------------------------------------------------------------------

_ONBOARD_WRITE_TOOLS = frozenset({"Write", "Edit", "MultiEdit", "NotebookEdit"})
_ONBOARD_ALLOWED_TOOLS = [
    "mcp__coding-os__*",
    "Write",
    "Edit",
    "MultiEdit",
    "Read",
    "Glob",
    "Grep",
    "TodoWrite",
    "WebFetch",
    "WebSearch",
]


def _is_path_under_docs(file_path: str, project_root: Path) -> bool:
    """True when file_path resolves to <project_root>/docs (or below)."""
    if not file_path:
        return False
    try:
        p = Path(file_path)
        if not p.is_absolute():
            p = project_root / p
        p = p.resolve()
        docs = (project_root / "docs").resolve()
        return p == docs or docs in p.parents
    except (OSError, ValueError, RuntimeError):
        return False


def _onboard_write_allowed(tool_input: dict, project_root: Path) -> bool:
    """Permission contract for the onboard session: a write tool may only target
    a path under docs/. Non-dict input or a missing path denies (fail-closed)."""
    if not isinstance(tool_input, dict):
        return False
    path = tool_input.get("file_path") or tool_input.get("path") or tool_input.get("notebook_path")
    return _is_path_under_docs(str(path or ""), project_root)


def _count_placeholder_todos(project_root: Path) -> tuple[int, bool]:
    """Scan docs/prd/*.md for scaffold `_TODO:` markers.

    Returns (todo_count, prd_exists). prd_exists=False means there is no PRD
    scaffold at all → nothing to onboard."""
    prd_dir = project_root / "docs" / "prd"
    if not prd_dir.is_dir():
        return 0, False
    total = 0
    found_any = False
    for md in prd_dir.glob("*.md"):
        found_any = True
        try:
            total += md.read_text(encoding="utf-8").count("_TODO:")
        except OSError as exc:
            logger.debug("onboarding scan skipped %s: %s", md, exc)
            continue
    return total, found_any


def _prd_touched_since(project_root: Path, marker: Path) -> bool:
    try:
        written_at = marker.stat().st_mtime
    except OSError:
        return False
    prd_dir = project_root / "docs" / "prd"
    for path in prd_dir.rglob("*.md"):
        try:
            if path.stat().st_mtime > written_at + 1:
                return True
        except OSError as exc:
            logger.debug("prd mtime check skipped %s: %s", path, exc)
    return False


def _onboarding_state(project_root: Path, state_dir: Path) -> dict:
    """Resolve onboarding completeness: onboarding.json override, else _TODO scan."""
    marker = state_dir / "onboarding.json"
    if marker.exists():
        try:
            data = json.loads(marker.read_text(encoding="utf-8"))
            completed = data.get("completed") if isinstance(data, dict) else None
            if completed is True:
                return {
                    "complete": True,
                    "source": "onboarding_json",
                    "placeholders_remaining": 0,
                    "reason": "marked onboarded",
                }
            # A `false` marker means "an intake seeded the PRD, so the placeholder
            # scan has nothing left to count" — pending, but it must expire on its
            # own: nothing writes `true` except the dismiss button, so a permanent
            # false would make finishing the guided interview change nothing.
            # Any edit under docs/prd/ after the marker was written IS the work.
            if completed is False and not _prd_touched_since(project_root, marker):
                return {
                    "complete": False,
                    "source": "onboarding_json",
                    "placeholders_remaining": _count_placeholder_todos(project_root)[0],
                    "reason": "intake captured — PRD not authored yet",
                }
        except (OSError, json.JSONDecodeError) as exc:
            logger.debug("onboarding.json unreadable: %s", exc)
    todos, prd_exists = _count_placeholder_todos(project_root)
    if not prd_exists:
        return {
            "complete": True,
            "source": "no_prd",
            "placeholders_remaining": 0,
            "reason": "no PRD scaffold to onboard",
        }
    return {
        "complete": todos == 0,
        "source": "placeholder_scan",
        "placeholders_remaining": todos,
        "reason": (
            "PRD still has scaffold _TODO markers" if todos else "PRD placeholders authored"
        ),
    }


@router.get("/onboarding-status")
def onboarding_status(
    _rl=Depends(make_rate_limit_dep("cognition.onboarding_status")),
    _m=Depends(make_metrics_dep("cognition.onboarding_status")),
):
    """Whether the project still needs onboarding (placeholder-scan first, onboarding.json override)."""
    from web._project_context import current_project_root  # type: ignore

    project = current_project_root()
    state = _state_dir()
    payload = _onboarding_state(project, state)
    payload["meta"] = {"layer": "cognition"}
    return unwrap(json.dumps({"ok": True, "data": payload}))


@router.post("/onboarding-status/dismiss")
def onboarding_dismiss(
    _rl=Depends(make_rate_limit_dep("cognition.onboarding_dismiss")),
    _m=Depends(make_metrics_dep("cognition.onboarding_dismiss")),
):
    """Persist the onboarding hero dismissal so it stops reappearing on reload."""
    state = _state_dir()
    marker = state / "onboarding.json"
    try:
        state.mkdir(parents=True, exist_ok=True)
        marker.write_text(
            json.dumps({"completed": True, "source": "dismissed"}, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        return unwrap(
            json.dumps(
                {
                    "ok": False,
                    "error": {
                        "category": "internal",
                        "retryable": False,
                        "message": f"could not write onboarding marker: {exc}",
                    },
                }
            )
        )
    return unwrap(
        json.dumps({"ok": True, "data": {"complete": True, "meta": {"layer": "cognition"}}})
    )


@router.post("/onboard")
async def onboard(
    body: dict = Body(...),
    _rl=Depends(make_rate_limit_dep("cognition.onboard")),
    _m=Depends(make_metrics_dep("cognition.onboard")),
):
    """Run the onboarder role with Write/Edit confined to docs/ (PreToolUse-gated). Claude-only."""
    prompt = str(body.get("prompt") or "").strip()
    if not prompt:
        return unwrap(
            json.dumps(
                {
                    "ok": False,
                    "error": {
                        "category": "validation",
                        "retryable": False,
                        "message": "prompt must be non-empty",
                    },
                }
            )
        )
    sdk = _claude_sdk()
    if sdk is None:
        return unwrap(_unavailable("claude_agent_sdk not installed"))

    import secrets
    import time as _time

    model = body.get("model") or None
    cwd = _project_cwd()
    project_root = Path(cwd)
    sid = f"ses-claude-onboard-{int(_time.time())}-{secrets.token_hex(3)}"
    system_prompt = _role_system_prompt("onboarder") or {
        "type": "preset",
        "preset": "claude_code",
    }

    async def _deny_non_docs_write(input_data: dict, _tool_use_id, _ctx) -> dict:
        # PreToolUse is evaluated FIRST and honored even under dontAsk (where
        # can_use_tool is skipped) — the only reliable place to path-scope writes.
        try:
            if input_data.get("tool_name") in _ONBOARD_WRITE_TOOLS and not _onboard_write_allowed(
                input_data.get("tool_input") or {}, project_root
            ):
                return {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": "onboard sessions may only write under docs/",
                    }
                }
        except Exception as exc:  # never raise from a hook — would kill the stream
            logger.debug("onboard PreToolUse gate error: %s", exc)
        return {}

    options = _build_agent_options(
        cwd=cwd,
        model=model,
        permission_mode="dontAsk",
        setting_sources=["project"],
        # No session_id — claude CLI requires a UUID; SDK mints its own (emitted below).
        include_partial_messages=True,  # token-by-token streaming for the live UI
        allowed_tools=list(_ONBOARD_ALLOWED_TOOLS),
        disallowed_tools=["Bash"],  # deny wins even over the allow-list
        system_prompt=system_prompt,
        # HookMatcher is the adapter SDK's type, constructed here because the hook
        # closure is core-local; ClaudeAgentOptions itself still routes through the
        # adapter seam. Migrating HookMatcher is tracked separately (out of scope).
        hooks={
            "PreToolUse": [
                sdk.HookMatcher(
                    matcher="Write|Edit|MultiEdit|NotebookEdit", hooks=[_deny_non_docs_write]
                )
            ]
        },
        max_turns=40,
    )

    async def event_gen():
        yield _sse_chunk("started", {"session_id": sid, "prompt": prompt[:200], "model": model})
        resolved_id = sid
        emitted_session = False
        try:
            async for event in sdk.query(prompt=prompt, options=options):
                if not emitted_session:
                    real_id = getattr(event, "session_id", None)
                    if real_id:
                        resolved_id = str(real_id)
                        yield _sse_chunk("session", {"session_id": resolved_id})
                        emitted_session = True
                kind = type(event).__name__.lower().replace("message", "") or "event"
                yield _sse_chunk(kind, _safe_serialize(event))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("onboard stream failed")
            yield _sse_chunk("error", {"message": str(exc)})
        if not emitted_session:
            yield _sse_chunk("session", {"session_id": resolved_id})
        yield _sse_chunk("done", {"session_id": resolved_id})

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.post("/chat/{session_id}/send")
async def chat_send(
    session_id: str,
    body: dict = Body(...),
    _rl=Depends(make_rate_limit_dep("cognition.chat_send")),
    _m=Depends(make_metrics_dep("cognition.chat_send")),
):
    """Resume a Claude session with a new prompt; stream events as SSE.

    Body: ``{"prompt": str, "fork": bool=false, "model": str|null}``.
    Each SSE event ``data`` payload is a serialized SDK message; ``event``
    field is one of ``user``, ``assistant``, ``system``, ``result``,
    ``stream``, ``rate_limit``, ``error``, ``done``.
    """
    prompt = str(body.get("prompt") or "").strip()
    if not prompt:
        return unwrap(
            json.dumps(
                {
                    "ok": False,
                    "error": {
                        "category": "validation",
                        "retryable": False,
                        "message": "prompt must be non-empty",
                    },
                }
            )
        )
    sdk = _claude_sdk()
    if sdk is None:
        return unwrap(_unavailable("claude_agent_sdk not installed"))

    cwd = _project_cwd()
    fork = bool(body.get("fork"))
    model = body.get("model") or None
    # SSOT builder (chat_resume profile) — same chat-light policy as chat_new
    # (mcp + deny floor + no Write/Edit), plus resume/fork for the follow-up turn.
    options = _chat_session_options(
        "chat_resume",
        cwd=cwd,
        model=model,
        system_prompt=_chat_system_prompt(model),
        resume=session_id,
        fork=fork,
    )

    async def event_gen():
        yield _sse_chunk(
            "started", {"session_id": session_id, "prompt": prompt[:200], "fork": fork}
        )
        _chat_presence_write(cwd, session_id, "prompt")
        emitted_kinds: list[str] = []
        try:
            async for event in sdk.query(prompt=prompt, options=options):
                kind = type(event).__name__.lower().replace("message", "")
                if not kind:
                    kind = "event"
                emitted_kinds.append(kind)
                logger.info(
                    "chat_send stream: session=%s kind=%s class=%s",
                    session_id,
                    kind,
                    type(event).__name__,
                )
                yield _sse_chunk(kind, _safe_serialize(event))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("chat resume stream failed")
            yield _sse_chunk("error", {"message": str(exc)})
        logger.info(
            "chat_send stream done: session=%s emitted=%s",
            session_id,
            ",".join(emitted_kinds) or "(none)",
        )
        _chat_presence_write(cwd, session_id, "stop")
        yield _sse_chunk("done", {"session_id": session_id})

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
