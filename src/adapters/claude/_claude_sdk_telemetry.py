"""Claude adapter — presence and cognition-trace side channels.

Both are fail-open observers of a dispatch: a presence file the Hub board reads
to show a live sub-agent, and an append-only trace the Hub tails to replay a
run. Neither may ever alter the returned EvidenceBundle, which is why they sit
outside the dispatch module rather than inside its try/finally.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger("coding_os.dispatcher.claude_sdk")


def _presence_write(
    project_root: Path, agent: str, session_id: str, event: str, pid: int | None = None
) -> None:
    """Write a single presence event for an SDK-spawned sub-agent."""
    import json as _json
    import os as _os
    import time as _time

    try:
        d = project_root / ".coding-os" / agent / "sessions"
        d.mkdir(parents=True, exist_ok=True)
        path = d / f"{session_id}.json"
        prev: dict[str, Any] = {}
        if path.exists():
            try:
                prev = _json.loads(path.read_text(encoding="utf-8"))
            except (OSError, _json.JSONDecodeError):
                prev = {}
        now = int(_time.time())
        # Schema parity with _helpers/presence_write.py (the canonical writer):
        # preserve model/sdk_uuid/used_tokens/context_updated_at so the Hub
        # reader resolves them for SDK sub-agents too (P5).
        new = {
            "agent": agent,
            "session_id": session_id,
            "pid": int(pid) if pid is not None else int(prev.get("pid") or _os.getpid()),
            "started_at": prev.get("started_at"),
            "last_prompt_at": prev.get("last_prompt_at"),
            "last_tool_at": prev.get("last_tool_at"),
            "last_stop_at": prev.get("last_stop_at"),
            "ended_at": prev.get("ended_at"),
            "model": prev.get("model"),
            "sdk_uuid": prev.get("sdk_uuid"),
            "used_tokens": prev.get("used_tokens"),
            "context_updated_at": prev.get("context_updated_at"),
        }
        if event == "start":
            new["started_at"] = now
            new["ended_at"] = None
            new["last_stop_at"] = None
        elif event == "prompt":
            new["last_prompt_at"] = now
            new["last_stop_at"] = None
            new["started_at"] = new["started_at"] or now
        elif event == "tool":
            new["last_tool_at"] = now
            new["started_at"] = new["started_at"] or now
        elif event == "stop":
            new["last_stop_at"] = now
        elif event == "end":
            new["ended_at"] = now
        # Keep the .json stem on the temp file (canonical writer uses
        # f"{path}.tmp.{pid}") so presence_gc reaps crash-orphaned temps (P31).
        tmp = path.parent / f"{path.name}.tmp.{_os.getpid()}"
        tmp.write_text(_json.dumps(new, separators=(",", ":")), encoding="utf-8")
        _os.replace(tmp, path)
    except OSError as exc:
        logger.debug("SDK presence write failed for %s: %s", session_id, exc)


def _dispatch_trace_content_enabled() -> bool:
    return os.environ.get("COS_DISPATCH_EVENT_CONTENT", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _emit_dispatch_trace(
    session_id: str, kind: str, formula_id: str | None, data: dict[str, Any] | None = None
) -> None:
    # Tee a dispatch lifecycle/turn event to the append-only cognition trace
    # sink (thinking_os.tracing) so the Hub can tail + replay the run. Fail-open:
    # a tracing failure must never alter the returned EvidenceBundle or break the
    # dispatch. Partial-message text rides along only when content is explicitly
    # enabled (COS_DISPATCH_EVENT_CONTENT), off by default.
    try:
        from thinking_os.tracing import emit

        emit(session_id, kind, data or {}, role=formula_id)
    except Exception as exc:
        logger.debug("dispatch trace emit skipped (%s): %s", kind, exc)
