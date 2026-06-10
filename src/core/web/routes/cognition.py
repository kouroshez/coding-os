"""core.web.routes.cognition — /api/cognition/* HTTP wrappers."""

from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from .._deps import make_metrics_dep, make_rate_limit_dep
from .._envelope import ENVELOPE_ERROR_RESPONSES, unwrap
from ._bounded_read import tail_lines

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


def _find_trace_file(
    state: Path, session_id: str, agent: str | None
) -> tuple[Path | None, str | None]:
    """Locate a session's jsonl trace file across all (or one) agent dir."""
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
    system_prompt = _role_system_prompt(role) or _chat_system_prompt(model)
    cwd = _project_cwd()
    new_session_id = f"ses-claude-ui-{int(_time.time())}-{secrets.token_hex(3)}"
    opts_kwargs: dict = dict(
        cwd=cwd,
        model=model,
        permission_mode="dontAsk",
        setting_sources=[],
        # Stream partial deltas so the UI paints the answer token-by-token (the
        # SDK otherwise yields one complete AssistantMessage at the end → the
        # whole reply appears at once). Emits StreamEvent frames carrying raw
        # Anthropic content_block_delta events.
        include_partial_messages=True,
        # Hub chat is a fast conversational surface — skip the project hook suite
        # (dozens of SessionStart hooks add ~40s of latency before the first
        # reply) and the auto-loaded CLAUDE.md governance/banner. The agent keeps
        # Read/Grep/Bash (incl. the `cos` CLI) to ground answers.
        # No session_id: the claude CLI rejects non-UUID ids ("Invalid session
        # ID. Must be a valid UUID"). The SDK mints its own UUID, surfaced below
        # from the stream and emitted as the `session` event.
    )
    opts_kwargs["system_prompt"] = system_prompt
    if effort:
        opts_kwargs["effort"] = effort
    options = sdk.ClaudeAgentOptions(**opts_kwargs)

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
    options = sdk.ClaudeAgentOptions(
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


def _onboarding_state(project_root: Path, state_dir: Path) -> dict:
    """Resolve onboarding completeness: onboarding.json override, else _TODO scan."""
    marker = state_dir / "onboarding.json"
    if marker.exists():
        try:
            data = json.loads(marker.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("completed") is True:
                return {"complete": True, "source": "onboarding_json", "placeholders_remaining": 0}
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

    options = sdk.ClaudeAgentOptions(
        cwd=cwd,
        model=model,
        permission_mode="dontAsk",
        setting_sources=["project"],
        # No session_id — claude CLI requires a UUID; SDK mints its own (emitted below).
        include_partial_messages=True,  # token-by-token streaming for the live UI
        allowed_tools=list(_ONBOARD_ALLOWED_TOOLS),
        disallowed_tools=["Bash"],  # deny wins even over the allow-list
        system_prompt=system_prompt,
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
    options = sdk.ClaudeAgentOptions(
        resume=session_id,
        cwd=cwd,
        fork_session=fork,
        model=model,
        # Headless resume has no interactive approver, so a write tool under the
        # default permission mode errors with "requested permissions … but you
        # haven't granted it yet". Match chat_new / onboard so Write/Edit/Bash run.
        permission_mode="dontAsk",
        # Follow-up turns must be as clean + fast as the first: no project hook
        # suite / CLAUDE.md governance (that caused the banner, "No response
        # requested", and tool-permission errors on resume).
        setting_sources=[],
        # Stream partial deltas so follow-up replies paint token-by-token too.
        include_partial_messages=True,
        system_prompt=_chat_system_prompt(model),
    )

    async def event_gen():
        yield _sse_chunk(
            "started", {"session_id": session_id, "prompt": prompt[:200], "fork": fork}
        )
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
