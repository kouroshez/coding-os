"""core.web.routes.hooks — /api/hooks/* HTTP wrappers (T19.4)."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, AsyncGenerator, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from .._deps import make_metrics_dep, make_rate_limit_dep
from .._envelope import ENVELOPE_ERROR_RESPONSES, unwrap

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

logger = logging.getLogger("coding_os.web.hooks")
router = APIRouter(prefix="/api/hooks", tags=["hooks"], responses=ENVELOPE_ERROR_RESPONSES)

_HOOK_LINE_RE = re.compile(
    r"^\[(?P<iso>[^\]]+)\]\s+\[(?P<hook>[^\]]+)\]\s+\[(?P<action>[^\]]+)\]"
    r"\s+agent=(?P<agent>\S+)\s+session=(?P<session>\S+)\s+task=(?P<task>\S+)"
    r"(?:\s+(?P<rest>.*))?$"
)


def _hook_log_path() -> Path:
    from web._project_context import current_project_root  # type: ignore
    override = os.environ.get("COS_HOOK_LOG")
    if override:
        return Path(override).resolve()
    return current_project_root() / ".coding-os" / ".hooks.log"


def _parse_hook_line(line: str) -> Optional[dict[str, Any]]:
    m = _HOOK_LINE_RE.match(line.strip())
    if not m:
        return None
    d = m.groupdict()
    rest = (d.get("rest") or "").strip()
    extras: dict[str, str] = {}
    if rest:
        for token in rest.split():
            if "=" in token:
                k, v = token.split("=", 1)
                extras[k] = v
    return {
        "iso_ts": d["iso"],
        "hook": d["hook"],
        "action": d["action"],
        "agent": d["agent"],
        "session_id": d["session"],
        "task": d["task"],
        "extras": extras,
    }


@router.get("/list")
async def list_hooks(
    adapter: Optional[str] = Query(None, description="Filter by adapter_scope (claude / codex / cursor)"),
    event: Optional[str] = Query(None, description="Filter by event (PreToolUse / Stop / …)"),
    _rl=Depends(make_rate_limit_dep("hooks.list")),
    _m=Depends(make_metrics_dep("hooks.list")),
):
    """List registered hooks with their event, matcher, scope, category."""
    try:
        from cli.hook_renderer import load_registry  # type: ignore[import]
    except ImportError as exc:
        return unwrap(json.dumps({
            "ok": False,
            "error": {"category": "unavailable", "retryable": False,
                      "message": f"hook_renderer not importable: {exc}"},
        }))

    # Registry SSOT lives at <repo>/core/hooks/registry.yaml.  Path
    # derivation mirrors cli/hook_renderer.py::main() so the route stays
    # in lockstep with the renderer.
    registry_path = _REPO_ROOT / "core" / "hooks" / "registry.yaml"
    try:
        entries = load_registry(registry_path)
    except Exception as exc:
        return unwrap(json.dumps({
            "ok": False,
            "error": {"category": "internal", "retryable": False, "message": str(exc)},
        }))

    # HookEntry fields (cli/hook_renderer.py::HookEntry):
    #   id, script, description, category, phase, events: list[dict], timeout, adapter_scope
    # Each entry registers one or more events; we explode them into rows so the
    # registry view shows one line per (hook_id, event, matcher) tuple — the
    # shape consumers (UI tables, audit scripts) actually want.
    rows: list[dict[str, Any]] = []
    for h in entries:
        scope = getattr(h, "adapter_scope", None)
        if adapter and scope and scope != adapter:
            continue
        ev_list = getattr(h, "events", []) or []
        if not ev_list:
            if event:
                continue
            rows.append({
                "name": h.id,
                "event": None,
                "matcher": None,
                "category": h.category,
                "phase": h.phase,
                "adapter_scope": scope,
                "script": h.script,
                "description": getattr(h, "description", ""),
            })
            continue
        for ev in ev_list:
            ev_name = ev.get("event") if isinstance(ev, dict) else None
            if event and ev_name != event:
                continue
            rows.append({
                "name": h.id,
                "event": ev_name,
                "matcher": ev.get("matcher") if isinstance(ev, dict) else None,
                "category": h.category,
                "phase": h.phase,
                "adapter_scope": scope,
                "script": h.script,
                "description": getattr(h, "description", ""),
            })

    return unwrap(json.dumps({
        "ok": True,
        "data": {"hooks": rows, "count": len(rows), "meta": {"layer": "hooks"}},
    }))


@router.get("/recent")
async def recent_hook_fires(
    limit: int = Query(50, ge=1, le=500),
    session_id: Optional[str] = Query(None),
    agent: Optional[str] = Query(None),
    _rl=Depends(make_rate_limit_dep("hooks.recent")),
    _m=Depends(make_metrics_dep("hooks.recent")),
):
    """Tail .coding-os/.hooks.log and return parsed events (newest first)."""
    log = _hook_log_path()
    if not log.exists():
        return unwrap(json.dumps({
            "ok": True,
            "data": {"events": [], "count": 0, "log_path": str(log),
                     "meta": {"layer": "hooks"}},
        }))
    try:
        lines = log.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError as exc:
        return unwrap(json.dumps({
            "ok": False,
            "error": {"category": "unavailable", "retryable": True, "message": str(exc)},
        }))
    parsed: list[dict[str, Any]] = []
    for line in reversed(lines):
        evt = _parse_hook_line(line)
        if evt is None:
            continue
        if session_id and evt["session_id"] != session_id:
            continue
        if agent and evt["agent"] != agent:
            continue
        parsed.append(evt)
        if len(parsed) >= limit:
            break
    return unwrap(json.dumps({
        "ok": True,
        "data": {
            "events": parsed,
            "count": len(parsed),
            "log_path": str(log),
            "log_size_bytes": log.stat().st_size,
            "meta": {"layer": "hooks"},
        },
    }))


@router.get("/stream")
async def stream_hooks(
    session_id: Optional[str] = Query(None),
    agent: Optional[str] = Query(None),
    _rl=Depends(make_rate_limit_dep("hooks.stream")),
    _m=Depends(make_metrics_dep("hooks.stream")),
):
    """SSE: tail the project hook log; emit one ``hook`` event per new line."""
    log = _hook_log_path()
    poll_secs = float(os.environ.get("COS_HOOK_STREAM_POLL_MS", "750")) / 1000.0
    heartbeat_secs = 15.0

    async def gen() -> AsyncGenerator[bytes, None]:
        yield f"event: connected\ndata: {json.dumps({'log_path': str(log)})}\n\n".encode()
        pos = log.stat().st_size if log.exists() else 0
        last_beat = time.monotonic()
        try:
            while True:
                if log.exists():
                    size = log.stat().st_size
                    if size < pos:
                        pos = 0  # log rotated
                    if size > pos:
                        with log.open("r", encoding="utf-8", errors="ignore") as fh:
                            fh.seek(pos)
                            chunk = fh.read()
                            pos = fh.tell()
                        for line in chunk.splitlines():
                            evt = _parse_hook_line(line)
                            if evt is None:
                                continue
                            if session_id and evt["session_id"] != session_id:
                                continue
                            if agent and evt["agent"] != agent:
                                continue
                            yield f"event: hook\ndata: {json.dumps(evt, ensure_ascii=False)}\n\n".encode()
                if time.monotonic() - last_beat > heartbeat_secs:
                    yield f"event: heartbeat\ndata: {json.dumps({'ts': int(time.time())})}\n\n".encode()
                    last_beat = time.monotonic()
                await asyncio.sleep(poll_secs)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("hook stream failed")
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
