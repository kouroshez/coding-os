"""core.web.routes.logs — /api/logs/* readers for the cos.log.jsonl sink."""

from __future__ import annotations

import asyncio
import calendar
import fnmatch
import json
import logging
import os
import re
import time
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, Query
from fastapi.responses import StreamingResponse

from .._deps import make_metrics_dep, make_rate_limit_dep
from .._envelope import ENVELOPE_ERROR_RESPONSES, unwrap

logger = logging.getLogger("coding_os.web.logs")
router = APIRouter(prefix="/api/logs", tags=["logs"], responses=ENVELOPE_ERROR_RESPONSES)

_LEVEL_FLOOR: dict[str, int] = {
    "debug": 10,
    "info": 20,
    "ok": 21,
    "warn": 30,
    "error": 40,
    "fatal": 50,
}

_DURATION_RE = re.compile(r"^\s*(\d+)\s*(ms|s|m|h|d)?\s*$", re.IGNORECASE)

# Browser-side errors beacon here; logging_os bridges this stdlib logger into the
# same cos.log.jsonl sink the GET readers serve, so client + server failures share
# one timeline (nothing in the SPA fails silently).
_client_logger = logging.getLogger("coding_os.web.client")
_CLIENT_LEVELS: dict[str, int] = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warn": logging.WARNING,
    "error": logging.ERROR,
}


def _jsonl_log_path() -> Path:
    from web._project_context import current_project_root  # type: ignore

    override = os.environ.get("COS_LOG_FILE")
    if override:
        return Path(override + ".jsonl").resolve()
    # Single-source the dir name + filename from logging_os.config so a rename
    # there cannot silently desync this reader (api-contract-discipline).
    from logging_os.config import LOG_BASENAME, STATE_DIR_NAME  # type: ignore

    return current_project_root() / STATE_DIR_NAME / (LOG_BASENAME + ".jsonl")


def _parse_duration_seconds(raw: str) -> float | None:
    match = _DURATION_RE.match(raw)
    if not match:
        return None
    value = float(match.group(1))
    unit = (match.group(2) or "s").lower()
    if unit == "ms":
        return value / 1000.0
    if unit == "s":
        return value
    if unit == "m":
        return value * 60.0
    if unit == "h":
        return value * 3600.0
    if unit == "d":
        return value * 86400.0
    return None


def _event_passes(
    event: dict[str, Any],
    *,
    level_floor: int,
    scope_pattern: str | None,
    earliest_epoch: float | None,
    search_lower: str | None,
) -> bool:
    level = str(event.get("lvl", "INFO")).lower()
    if _LEVEL_FLOOR.get(level, 20) < level_floor:
        return False
    if scope_pattern and not fnmatch.fnmatch(str(event.get("scope", "")), scope_pattern):
        return False
    if earliest_epoch is not None:
        ts_str = str(event.get("ts", ""))
        try:
            ts_epoch = calendar.timegm(time.strptime(ts_str, "%Y-%m-%dT%H:%M:%SZ"))
        except (ValueError, TypeError):
            ts_epoch = None
        if ts_epoch is not None and ts_epoch < earliest_epoch:
            return False
    if search_lower:
        msg = str(event.get("msg", "")).lower()
        if search_lower not in msg:
            return False
    return True


def _read_tail_jsonl(path: Path, max_lines: int) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            lines = handle.readlines()
    except OSError as exc:
        logger.warning("logs tail read failed: %s", exc)
        return []
    tail = lines[-max_lines:] if len(lines) > max_lines else lines
    parsed: list[dict[str, Any]] = []
    for raw in tail:
        line = raw.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            parsed.append(obj)
    return parsed


@router.post("/client")
async def report_client_log(
    body: dict = Body(...),
    _rl=Depends(make_rate_limit_dep("logs.client")),
    _m=Depends(make_metrics_dep("logs.client")),
) -> Any:
    """Record a browser-side log/error into the server log sink (logging_os)."""
    message = str(body.get("message") or "").strip()
    if not message:
        return unwrap(
            json.dumps(
                {
                    "ok": False,
                    "error": {
                        "category": "validation",
                        "retryable": False,
                        "message": "message is required",
                    },
                }
            )
        )
    log_level = _CLIENT_LEVELS.get(str(body.get("level") or "error").lower(), logging.ERROR)
    # Bound every field — a client beacon must never bloat or break the sink.
    message = message[:2000]
    url = str(body.get("url") or "")[:500]
    context_raw = body.get("context")
    if context_raw is None:
        context = "-"
    elif isinstance(context_raw, (str, int, float, bool)):
        context = str(context_raw)[:2000]
    else:
        try:
            context = json.dumps(context_raw)[:2000]
        except Exception:
            context = str(context_raw)[:2000]
    _client_logger.log(log_level, "client: %s | url=%s | context=%s", message, url or "-", context)
    return unwrap(
        json.dumps(
            {
                "ok": True,
                "data": {
                    "recorded": True,
                    "meta": {"layer": "observability", "source": "client"},
                },
            }
        )
    )


@router.get("/recent")
async def recent_logs(
    limit: int = Query(200, ge=1, le=2000),
    level: str = Query("debug", description="floor — events at or above this level"),
    scope: str | None = Query(None, description="fnmatch glob, e.g. hook.* or core.thinking_os.*"),
    since: str | None = Query(None, description="relative duration: 30s, 10m, 1h, 2d"),
    search: str | None = Query(None, description="substring match on msg (case-insensitive)"),
    _rl=Depends(make_rate_limit_dep("logs.recent")),
    _m=Depends(make_metrics_dep("logs.recent")),
):
    """Tail .cos.log.jsonl and return parsed events (newest last)."""
    path = _jsonl_log_path()
    level_floor = _LEVEL_FLOOR.get(level.lower(), 10)
    earliest_epoch: float | None = None
    if since:
        seconds = _parse_duration_seconds(since)
        if seconds is not None:
            earliest_epoch = time.time() - seconds
    search_lower = search.lower() if search else None

    events = _read_tail_jsonl(path, max_lines=limit * 4)
    filtered = [
        evt
        for evt in events
        if _event_passes(
            evt,
            level_floor=level_floor,
            scope_pattern=scope,
            earliest_epoch=earliest_epoch,
            search_lower=search_lower,
        )
    ]
    if len(filtered) > limit:
        filtered = filtered[-limit:]

    return unwrap(
        json.dumps(
            {
                "ok": True,
                "data": {
                    "events": filtered,
                    "count": len(filtered),
                    "log_path": str(path),
                    "log_size_bytes": path.stat().st_size if path.exists() else 0,
                    "meta": {"layer": "logs"},
                },
            }
        )
    )


@router.get("/summary")
async def logs_summary(
    since: str | None = Query("1h", description="relative duration window: 30s, 10m, 1h, 2d"),
    _rl=Depends(make_rate_limit_dep("logs.summary")),
    _m=Depends(make_metrics_dep("logs.summary")),
):
    """Counts-by-level + top error scopes over the recent log feed — the 'what is broken now' rollup."""
    path = _jsonl_log_path()
    earliest_epoch: float | None = None
    if since:
        seconds = _parse_duration_seconds(since)
        if seconds is not None:
            earliest_epoch = time.time() - seconds

    by_level: dict[str, int] = {}
    scopes: dict[str, int] = {}
    for evt in _read_tail_jsonl(path, max_lines=8000):
        if not _event_passes(
            evt, level_floor=10, scope_pattern=None,
            earliest_epoch=earliest_epoch, search_lower=None,
        ):
            continue
        lvl = str(evt.get("lvl", "INFO")).upper()
        by_level[lvl] = by_level.get(lvl, 0) + 1
        if _LEVEL_FLOOR.get(lvl.lower(), 0) >= _LEVEL_FLOOR["error"]:
            scope = str(evt.get("scope", "?"))
            scopes[scope] = scopes.get(scope, 0) + 1

    top = sorted(scopes.items(), key=lambda kv: -kv[1])[:10]
    return unwrap(
        json.dumps(
            {
                "ok": True,
                "data": {
                    "by_level": by_level,
                    "error_count": by_level.get("ERROR", 0),
                    "warn_count": by_level.get("WARN", 0),
                    "fatal_count": by_level.get("FATAL", 0),
                    "top_error_scopes": [{"scope": s, "count": c} for s, c in top],
                    "log_path": str(path),
                    "meta": {"layer": "logs"},
                },
            }
        )
    )


@router.get("/stream")
async def stream_logs(
    level: str = Query("debug"),
    scope: str | None = Query(None),
    search: str | None = Query(None),
    _rl=Depends(make_rate_limit_dep("logs.stream")),
    _m=Depends(make_metrics_dep("logs.stream")),
):
    """SSE: tail .cos.log.jsonl; emit one ``log`` event per new line."""
    path = _jsonl_log_path()
    level_floor = _LEVEL_FLOOR.get(level.lower(), 10)
    search_lower = search.lower() if search else None
    poll_secs = float(os.environ.get("COS_LOG_STREAM_POLL_MS", "750")) / 1000.0
    heartbeat_secs = 15.0

    async def gen() -> AsyncGenerator[bytes, None]:
        yield f"event: connected\ndata: {json.dumps({'log_path': str(path)})}\n\n".encode()
        pos = path.stat().st_size if path.exists() else 0
        last_beat = time.monotonic()
        try:
            while True:
                if path.exists():
                    size = path.stat().st_size
                    if size < pos:
                        pos = 0
                    if size > pos:
                        with path.open("r", encoding="utf-8", errors="ignore") as fh:
                            fh.seek(pos)
                            chunk = fh.read()
                            pos = fh.tell()
                        for raw in chunk.splitlines():
                            line = raw.strip()
                            if not line:
                                continue
                            try:
                                evt = json.loads(line)
                            except json.JSONDecodeError:
                                continue
                            if not isinstance(evt, dict):
                                continue
                            if not _event_passes(
                                evt,
                                level_floor=level_floor,
                                scope_pattern=scope,
                                earliest_epoch=None,
                                search_lower=search_lower,
                            ):
                                continue
                            yield f"event: log\ndata: {json.dumps(evt, ensure_ascii=False)}\n\n".encode()
                if time.monotonic() - last_beat > heartbeat_secs:
                    yield f"event: heartbeat\ndata: {json.dumps({'ts': int(time.time())})}\n\n".encode()
                    last_beat = time.monotonic()
                await asyncio.sleep(poll_secs)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("log stream failed")
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
