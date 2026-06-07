"""core.web.routes.observability — unified sessions/hooks/cognition APIs.

PURPOSE: Provide one backend surface for Hub observability timeline UI.
INPUT:   HTTP query params for session filtering and pagination.
OUTPUT:  JSON envelope {data, meta} with session index + mixed event timeline.
DEPENDENCIES: fastapi, pathlib, json, core.web._envelope.
NOTES:   Reads from `.coding-os/<agent>/{sessions,traces}` and `.coding-os/.hooks.log`.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Query

from .._deps import make_metrics_dep, make_rate_limit_dep
from .._envelope import ENVELOPE_ERROR_RESPONSES, unwrap
from ._bounded_read import newest_files, tail_lines

# Scale guards (TASK-225): never glob every trace file or read a whole log.
_MAX_TRACE_FILES = 100  # newest-N trace files to scan per directory

router = APIRouter(
    prefix="/api/observability", tags=["observability"], responses=ENVELOPE_ERROR_RESPONSES
)

_HOOK_RE = re.compile(
    r"^\[(?P<iso>[^\]]+)\]\s+\[(?P<hook>[^\]]+)\]\s+\[(?P<action>[^\]]+)\]"
    r"\s+agent=(?P<agent>\S+)\s+session=(?P<session>\S+)\s+task=(?P<task>\S+)"
    r"(?:\s+model=(?P<model>\S+))?(?:\s+(?P<detail>.*))?$"
)


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


def _fmt_ts(ts: float | int | None) -> str | None:
    if ts is None:
        return None
    try:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(float(ts)))
    except Exception:
        return None


def _friendly_session_label(session_id: str, agent: str, started_at: float | int | None) -> str:
    parts = session_id.split("-")
    if len(parts) >= 5 and parts[0] == "ses":
        maybe_date = parts[2]
        maybe_time = parts[3]
        if (
            len(maybe_date) == 8
            and len(maybe_time) == 6
            and maybe_date.isdigit()
            and maybe_time.isdigit()
        ):
            return f"{agent} {maybe_date[0:4]}-{maybe_date[4:6]}-{maybe_date[6:8]} {maybe_time[0:2]}:{maybe_time[2:4]}"
    ts_fmt = _fmt_ts(started_at)
    return f"{agent} {ts_fmt}" if ts_fmt else session_id


def _is_active_session(row: dict[str, Any]) -> bool:
    if row.get("ended_at"):
        return False
    now = time.time()
    last_activity = (
        row.get("last_tool_at") or row.get("last_prompt_at") or row.get("started_at") or 0
    )
    last_stop = row.get("last_stop_at") or 0
    try:
        return float(last_activity) >= float(last_stop) and (now - float(last_activity)) <= 120.0
    except Exception:
        return False


def _scan_sessions(state: Path, agent_filter: str | None = None) -> list[dict[str, Any]]:
    if not state.exists() or not state.is_dir():
        return []
    traces_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    sessions_by_key: dict[tuple[str, str], dict[str, Any]] = {}

    def _scan_agent_dir(agent_dir: Path, agent_name: str) -> None:
        traces_dir = agent_dir / "traces"
        if traces_dir.exists():
            for f in newest_files(traces_dir, "*.jsonl", _MAX_TRACE_FILES):
                st = f.stat()
                traces_by_key[(agent_name, f.stem)] = {
                    "agent": agent_name,
                    "session_id": f.stem,
                    "trace_path": str(f),
                    "size_bytes": st.st_size,
                    "modified_ts": st.st_mtime,
                    "has_trace": True,
                }
        sessions_dir = agent_dir / "sessions"
        if not sessions_dir.exists():
            return
        for meta in newest_files(sessions_dir, "ses-*.json", _MAX_TRACE_FILES):
            try:
                payload = json.loads(meta.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            sid = str(payload.get("session_id") or meta.stem)
            started = payload.get("started_at")
            sessions_by_key[(agent_name, sid)] = {
                "agent": agent_name,
                "session_id": sid,
                "started_at": started,
                "last_prompt_at": payload.get("last_prompt_at"),
                "last_tool_at": payload.get("last_tool_at"),
                "last_stop_at": payload.get("last_stop_at"),
                "ended_at": payload.get("ended_at"),
                "display_name": _friendly_session_label(sid, agent_name, started),
                "has_trace": False,
            }

    if agent_filter:
        _scan_agent_dir(state / agent_filter, agent_filter)
    else:
        for candidate in state.iterdir():
            if candidate.is_dir():
                _scan_agent_dir(candidate, candidate.name)

    merged: list[dict[str, Any]] = []
    keys = set(traces_by_key) | set(sessions_by_key)
    for key in keys:
        tr = traces_by_key.get(key, {})
        se = sessions_by_key.get(key, {})
        row = {
            **se,
            **tr,
            "agent": key[0],
            "session_id": key[1],
            "display_name": se.get("display_name") or key[1],
            "has_trace": bool(tr),
            "source": "trace+session" if tr and se else ("trace-only" if tr else "session-only"),
        }
        row["is_active"] = _is_active_session(row)
        merged.append(row)

    def _newest_ts(row: dict[str, Any]) -> float:
        # Sort by the MOST RECENT signal, not whichever happens to be set
        # first.  The previous `or`-chain would stick at `last_tool_at`
        # even when `last_prompt_at` was hours newer — current sessions
        # ended up buried under stale tool-only sessions.
        candidates = (
            row.get("modified_ts"),
            row.get("last_tool_at"),
            row.get("last_prompt_at"),
            row.get("last_stop_at"),
            row.get("started_at"),
        )
        return max((float(c) for c in candidates if c is not None), default=0.0)

    merged.sort(
        key=lambda row: (
            0 if row.get("is_active") else 1,
            -_newest_ts(row),
        )
    )
    return merged


def _session_agent_from_id(session_id: str) -> str | None:
    parts = session_id.split("-", 3)
    if len(parts) < 3 or parts[0] != "ses":
        return None
    agent = parts[1].strip().lower()
    return agent or None


def _parse_iso_ts(value: str | None) -> float | None:
    """Parse a UTC-suffixed ISO timestamp (`...Z`) to a Unix epoch float.

    `time.mktime` would treat the parsed struct_time as LOCAL time and
    bake the server's TZ offset into the returned epoch — observed in
    the wild as a 3-4h drift on the Hub UI when the server runs outside
    UTC.  `calendar.timegm` is the correct UTC inverse of strptime.
    """
    if not value:
        return None
    try:
        import calendar

        return float(calendar.timegm(time.strptime(value, "%Y-%m-%dT%H:%M:%SZ")))
    except Exception:
        return None


def _read_hook_events(state: Path, session_id: str | None, limit: int) -> list[dict[str, Any]]:
    hook_log = Path(os.environ.get("COS_HOOK_LOG") or (state / ".hooks.log"))
    if not hook_log.exists():
        return []
    events: list[dict[str, Any]] = []
    lines, _ = tail_lines(hook_log)  # bounded tail — never load a multi-GB hook log
    for line in lines:
        m = _HOOK_RE.match(line.strip())
        if not m:
            continue
        d = m.groupdict()
        if session_id and d.get("session") != session_id:
            continue
        ts = _parse_iso_ts(d.get("iso"))
        events.append(
            {
                "source": "hook",
                "kind": d.get("hook"),
                "status": d.get("action"),
                "ts": ts,
                "iso_ts": d.get("iso"),
                "session_id": d.get("session"),
                "agent": d.get("agent"),
                "summary": f"{d.get('hook')} · {d.get('action')}",
                "data": {
                    "task": d.get("task"),
                    "model": d.get("model"),
                    "detail": d.get("detail") or "",
                },
            }
        )
    events.sort(key=lambda e: float(e.get("ts") or 0.0), reverse=True)
    return events[:limit]


def _read_cognition_events(state: Path, session_id: str | None, limit: int) -> list[dict[str, Any]]:
    if not state.exists() or not state.is_dir():
        return []
    events: list[dict[str, Any]] = []
    files: list[Path] = []
    if session_id:
        guess_agent = _session_agent_from_id(session_id)
        if guess_agent:
            candidate = state / guess_agent / "traces" / f"{session_id}.jsonl"
            if candidate.exists():
                files = [candidate]
        if not files:
            for agent_dir in state.iterdir():
                if not agent_dir.is_dir():
                    continue
                candidate = agent_dir / "traces" / f"{session_id}.jsonl"
                if candidate.exists():
                    files = [candidate]
                    break
    else:
        for agent_dir in state.iterdir():
            if not agent_dir.is_dir():
                continue
            trace_dir = agent_dir / "traces"
            if not trace_dir.exists():
                continue
            files.extend(newest_files(trace_dir, "*.jsonl", _MAX_TRACE_FILES))

    for trace_file in files:
        agent = trace_file.parent.parent.name
        sid = trace_file.stem
        trace_lines, _ = tail_lines(trace_file)
        for line in trace_lines:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            kind = str(payload.get("kind") or "event")
            ts = payload.get("ts")
            events.append(
                {
                    "source": "cognition",
                    "kind": kind,
                    "status": payload.get("status"),
                    "ts": float(ts) if isinstance(ts, (int, float)) else None,
                    "iso_ts": None,
                    "session_id": sid,
                    "agent": str(payload.get("agent") or agent),
                    "summary": kind.replace("_", " "),
                    "data": payload.get("data")
                    if isinstance(payload.get("data"), dict)
                    else payload,
                }
            )
    events.sort(key=lambda e: float(e.get("ts") or 0.0), reverse=True)
    return events[:limit]


@router.get("/sessions")
async def list_sessions(
    agent: str | None = Query(None),
    _rl=Depends(make_rate_limit_dep("observability.sessions")),
    _m=Depends(make_metrics_dep("observability.sessions")),
):
    state = _state_dir()
    sessions = _scan_sessions(state, agent_filter=agent)
    return unwrap(
        json.dumps(
            {
                "ok": True,
                "data": {
                    "sessions": sessions,
                    "count": len(sessions),
                    "active_count": sum(1 for row in sessions if row.get("is_active")),
                    "trace_count": sum(1 for row in sessions if row.get("has_trace")),
                    "meta": {"layer": "observability"},
                },
            }
        )
    )


@router.get("/timeline")
async def timeline(
    session_id: str | None = Query(None),
    sources: str = Query("hook,cognition"),
    limit: int = Query(200, ge=1, le=2000),
    _rl=Depends(make_rate_limit_dep("observability.timeline")),
    _m=Depends(make_metrics_dep("observability.timeline")),
):
    state = _state_dir()
    source_set = {s.strip().lower() for s in sources.split(",") if s.strip()}
    events: list[dict[str, Any]] = []
    if "hook" in source_set:
        events.extend(_read_hook_events(state, session_id=session_id, limit=limit))
    if "cognition" in source_set:
        events.extend(_read_cognition_events(state, session_id=session_id, limit=limit))
    events.sort(key=lambda e: float(e.get("ts") or 0.0), reverse=True)
    events = events[:limit]
    return unwrap(
        json.dumps(
            {
                "ok": True,
                "data": {
                    "session_id": session_id,
                    "sources": sorted(source_set),
                    "events": events,
                    "count": len(events),
                    "meta": {"layer": "observability"},
                },
            }
        )
    )
