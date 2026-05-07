"""core.web.routes.cognition — /api/cognition/* HTTP wrappers."""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import sys
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from .._deps import make_metrics_dep, make_rate_limit_dep
from .._envelope import unwrap

logger = logging.getLogger(__name__)

_CORE_DIR = Path(__file__).resolve().parents[3]
if str(_CORE_DIR) not in sys.path:
    sys.path.insert(0, str(_CORE_DIR))

router = APIRouter(prefix="/api/cognition", tags=["cognition"])


def _state_dir() -> Path:
    """Resolve the .coding-os state directory."""
    base = os.environ.get("COS_STATE_DIR") or os.environ.get("COS_AGENT_DIR")
    if base:
        return Path(base).resolve()
    from web._project_context import current_project_root

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
    return json.dumps({
        "ok": False,
        "error": {"category": "unavailable", "retryable": False, "message": msg},
    })


@router.get("/traces")
async def list_traces(
    agent: Optional[str] = Query(None, description="Agent name (e.g. 'claude')"),
    _rl=Depends(make_rate_limit_dep("cognition.traces")),
    _m=Depends(make_metrics_dep("cognition.traces")),
):
    """List available trace sessions."""
    state = _state_dir()
    sessions = []

    def _scan_agent_dir(agent_dir: Path, agent_name: str) -> None:
        traces_dir = agent_dir / "traces"
        if not traces_dir.exists():
            return
        for f in sorted(traces_dir.glob("*.jsonl")):
            sessions.append({
                "agent": agent_name,
                "session_id": f.stem,
                "path": str(f),
                "size_bytes": f.stat().st_size,
            })

    if agent:
        _scan_agent_dir(state / agent, agent)
    else:
        for candidate in state.iterdir():
            if candidate.is_dir():
                _scan_agent_dir(candidate, candidate.name)

    return unwrap(json.dumps({
        "ok": True,
        "data": {"sessions": sessions, "count": len(sessions), "meta": {"layer": "cognition"}},
    }))


@router.get("/trace/{session_id}")
async def get_trace(
    session_id: str,
    agent: Optional[str] = Query(None),
    _rl=Depends(make_rate_limit_dep("cognition.trace")),
    _m=Depends(make_metrics_dep("cognition.trace")),
):
    """Read a single cognition trace file as a list of events."""
    state = _state_dir()
    target: Path | None = None

    if agent:
        candidate = state / agent / "traces" / f"{session_id}.jsonl"
        if candidate.exists():
            target = candidate
    else:
        for agent_dir in state.iterdir():
            if not agent_dir.is_dir():
                continue
            candidate = agent_dir / "traces" / f"{session_id}.jsonl"
            if candidate.exists():
                target = candidate
                break

    if target is None:
        raise HTTPException(status_code=404, detail=f"trace {session_id!r} not found")

    events = []
    for line in target.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            events.append({"raw": line})

    return unwrap(json.dumps({
        "ok": True,
        "data": {
            "session_id": session_id,
            "events": events,
            "count": len(events),
            "meta": {"layer": "cognition"},
        },
    }))


# ---------------------------------------------------------------------------
# T2.4 / T19.1 — Dispatcher cost panel (Phase Q.deep)
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
    except Exception as exc:  # noqa: BLE001
        logger.debug("project-root db path resolve failed: %s", exc)
    return None


@router.get("/cost")
async def dispatcher_cost_summary(
    formula_id: Optional[str] = Query(None, description="Filter to one formula"),
    limit: int = Query(50, ge=1, le=500),
    _rl=Depends(make_rate_limit_dep("cognition.cost")),
    _m=Depends(make_metrics_dep("cognition.cost")),
):
    """Aggregate dispatch cost rolled up by formula and day (T2.4)."""
    db = _db_path()
    if db is None:
        return unwrap(json.dumps({
            "ok": True,
            "data": {"rows": [], "total_usd": 0.0, "count": 0,
                     "meta": {"layer": "cognition"}},
        }))

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
        return unwrap(json.dumps({
            "ok": False,
            "error": {"category": "internal", "retryable": False, "message": str(exc)},
        }))

    return unwrap(json.dumps({
        "ok": True,
        "data": {
            "rows": rows,
            "total_usd": round(total_usd, 6),
            "count": len(rows),
            "meta": {"layer": "cognition"},
        },
    }))


@router.get("/dispatchers")
async def list_dispatchers(
    limit: int = Query(100, ge=1, le=1000),
    status: Optional[str] = Query(None),
    _rl=Depends(make_rate_limit_dep("cognition.dispatchers")),
    _m=Depends(make_metrics_dep("cognition.dispatchers")),
):
    """List recent formula dispatches with telemetry (T19.1)."""
    db = _db_path()
    if db is None:
        return unwrap(json.dumps({
            "ok": True,
            "data": {"dispatches": [], "count": 0, "meta": {"layer": "cognition"}},
        }))

    try:
        params: list = []
        where = "WHERE cost_usd IS NOT NULL"
        if status:
            where += " AND status = ?"
            params.append(status)
        params.append(limit)
        with sqlite3.connect(db) as conn:
            conn.row_factory = sqlite3.Row
            rows = [dict(r) for r in conn.execute(
                f"SELECT session_id, formula_id, ts, cost_usd, budget_usd, "
                f"status, latency_ms "
                f"FROM formula_dispatches {where} "
                f"ORDER BY ts DESC LIMIT ?",
                params,
            ).fetchall()]
    except Exception as exc:
        return unwrap(json.dumps({
            "ok": False,
            "error": {"category": "internal", "retryable": False, "message": str(exc)},
        }))

    return unwrap(json.dumps({
        "ok": True,
        "data": {"dispatches": rows, "count": len(rows), "meta": {"layer": "cognition"}},
    }))


@router.get("/dispatchers/{session_id}/tools")
async def dispatcher_tools(
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
    return unwrap(json.dumps({
        "ok": True,
        "data": {
            "session_id": session_id,
            "tool_calls": tool_calls,
            "failures": failures,
            "count": len(tool_calls),
            "meta": {"layer": "cognition"},
        },
    }))


@router.get("/analyze")
async def cognition_analyze(
    task_description: str = Query(...),
    complexity_hint: Optional[str] = Query(None),
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
        return unwrap(json.dumps({
            "ok": False,
            "error": {"category": "internal", "retryable": False, "message": str(exc)},
        }))
    return unwrap(_unavailable("analyze_task not available in this cognition module version"))
