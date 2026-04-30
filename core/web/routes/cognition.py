"""core.web.routes.cognition — /api/cognition/* HTTP wrappers.

PURPOSE: Expose cos_cognition_* MCP tools and trace file reading as HTTP
         endpoints so the SPA can render the cognition timeline page (S5).
INPUT:   HTTP request query params matching each tool's signature.
OUTPUT:  JSON response unwrapped from the MCP envelope ({data, meta} on 200).
DEPENDENCIES: fastapi, core.web._envelope, core.thinking_os tools,
              pathlib (trace file reading).
NOTES:  Trace files live at .coding-os/<agent>/traces/<session_id>.jsonl.
        The reader endpoint scans the directory and streams JSONL lines as a
        list so the SPA doesn't need to parse JSONL itself.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from .._deps import make_metrics_dep, make_rate_limit_dep
from .._envelope import unwrap

_CORE_DIR = Path(__file__).resolve().parents[3]
if str(_CORE_DIR) not in sys.path:
    sys.path.insert(0, str(_CORE_DIR))

router = APIRouter(prefix="/api/cognition", tags=["cognition"])


def _state_dir() -> Path:
    """Resolve the .coding-os state directory.

    PURPOSE: Find where cognition traces live on this machine.
    INPUT:   COS_STATE_DIR or COS_AGENT_DIR env vars, fallback to .coding-os.
    OUTPUT:  Path to the .coding-os directory.
    DEPENDENCIES: os.environ.
    NOTES:   Uses COS_STATE_DIR when set (multi-agent deployments).
    """
    base = os.environ.get("COS_STATE_DIR") or os.environ.get("COS_AGENT_DIR")
    if base:
        return Path(base).resolve()
    from web._project_context import current_project_root

    return current_project_root() / ".coding-os"


def _cognition_module():
    """Lazy import for cognition tools.

    PURPOSE: Defer import so web package boots when cognition extras absent.
    INPUT:   none.
    OUTPUT:  tools.cognition module or None.
    DEPENDENCIES: core.thinking_os.tools.cognition.
    NOTES:   Module cached by Python after first import.
    """
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
    """List available trace sessions.

    PURPOSE: Scan .coding-os/<agent>/traces/ and return session IDs.
    INPUT:   agent (optional, defaults to scanning all subdirs).
    OUTPUT:  {data: {sessions: [{agent, session_id, path, size_bytes}]}, meta}.
    DEPENDENCIES: pathlib, os.
    NOTES:   Returns empty list when no traces directory exists; never 404.
    """
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
    """Read a single cognition trace file as a list of events.

    PURPOSE: Parse .coding-os/<agent>/traces/<session_id>.jsonl into events.
    INPUT:   session_id (path param), agent (optional query param).
    OUTPUT:  {data: {session_id, events, count}, meta} on 200.
    DEPENDENCIES: pathlib, json.
    NOTES:   Scans all agent dirs when agent is not specified.
    """
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


@router.get("/analyze")
async def cognition_analyze(
    task_description: str = Query(...),
    complexity_hint: Optional[str] = Query(None),
    _rl=Depends(make_rate_limit_dep("cognition.analyze")),
    _m=Depends(make_metrics_dep("cognition.analyze")),
):
    """Analyze a task via cos_analyze_task.

    PURPOSE: HTTP wrapper for cos_analyze_task cognition tool.
    INPUT:   task_description, complexity_hint.
    OUTPUT:  {data: {analysis, ...}, meta} on 200.
    DEPENDENCIES: core.thinking_os.tools.cognition.
    NOTES:   Returns 503 if cognition tools are unavailable.
    """
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
