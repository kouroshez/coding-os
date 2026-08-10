"""/api/cognition chat routes — sessions, roles, and the streaming send path.

Split from cognition.py because chat changes with the Claude SDK surface (block
shapes, session options, streaming) while traces and cost change with the
dispatcher's own telemetry. Both attach to the same router, so the URL surface
is byte-identical to before the split.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
import sqlite3
import sys
from pathlib import Path
from typing import Any

from fastapi import Body, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from .._deps import make_metrics_dep, make_rate_limit_dep
from .._envelope import unwrap
from .cognition import _auto_route_model, _db_path, _state_dir, _unavailable, router

logger = logging.getLogger(__name__)

_CORE_DIR = Path(__file__).resolve().parents[3]
if str(_CORE_DIR) not in sys.path:
    sys.path.insert(0, str(_CORE_DIR))


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
    kwargs = {
        "cwd": cwd,
        "model": model,
        "permission_mode": "dontAsk",
        "setting_sources": [],
        "include_partial_messages": True,
        "system_prompt": system_prompt,
    }
    if effort:
        kwargs["effort"] = effort
    if profile == "chat_resume":
        if resume:
            kwargs["resume"] = resume
        kwargs["fork_session"] = fork
    return _build_agent_options(**kwargs)


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
        "agent": "claude",
        "writable": True,
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


def _session_agent_hints(session_id: str) -> set[str]:
    hints: set[str] = set()
    state = _state_dir()
    if not state.is_dir():
        return hints
    for agent_dir in state.iterdir():
        sessions_dir = agent_dir / "sessions"
        if not sessions_dir.is_dir():
            continue
        for path in sessions_dir.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if payload.get("sdk_uuid") == session_id:
                hints.add(str(payload.get("agent") or agent_dir.name))
    return hints


@router.get("/chats")
async def list_chats(
    limit: int = Query(50, ge=1, le=500),
    _rl=Depends(make_rate_limit_dep("cognition.chats")),
    _m=Depends(make_metrics_dep("cognition.chats")),
):
    """List chat sessions from every available transcript provider."""
    from web.chat_providers import list_sessions as list_adapter_sessions

    cwd = _project_cwd()
    adapter_rows, adapter_sources = await list_adapter_sessions(cwd, limit)
    rows_by_id = {str(row["session_id"]): row for row in adapter_rows}
    sources = [f"{agent}_sdk" for agent in adapter_sources]
    sdk = _claude_sdk()
    if sdk is not None:
        try:
            sessions = sdk.list_sessions(directory=cwd, limit=limit)
        except Exception as exc:
            logger.warning("Claude chat list failed: %s", exc)
        else:
            for session in sessions:
                row = _serialize_session_info(session)
                rows_by_id.setdefault(str(row["session_id"]), row)
            sources.append("claude_agent_sdk")
    if not sources:
        return unwrap(_unavailable("no chat transcript provider is available"))
    rows = list(rows_by_id.values())
    rows.sort(key=lambda r: r.get("last_modified") or 0, reverse=True)
    rows = rows[:limit]
    return unwrap(
        json.dumps(
            {
                "ok": True,
                "data": {
                    "sessions": rows,
                    "count": len(rows),
                    "cwd": cwd,
                    "meta": {"layer": "cognition", "sources": sources},
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
async def get_chat(
    session_id: str,
    limit: int = Query(500, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    _rl=Depends(make_rate_limit_dep("cognition.chat_get")),
    _m=Depends(make_metrics_dep("cognition.chat_get")),
):
    """Return one adapter-normalized transcript."""
    from web.chat_providers import get_session as get_adapter_session

    cwd = _project_cwd()
    agent_hints = _session_agent_hints(session_id)
    if agent_hints and "claude" not in agent_hints:
        adapter_data = await get_adapter_session(
            session_id, cwd, limit, offset, agent_hints=agent_hints
        )
        if adapter_data is not None:
            return unwrap(json.dumps({"ok": True, "data": adapter_data}))

    sdk = _claude_sdk()
    info = None
    if sdk is not None:
        try:
            info = sdk.get_session_info(session_id, directory=cwd)
        except Exception as exc:
            logger.warning("get_session_info(%s) failed: %s", session_id, exc)
    if info is None:
        adapter_data = await get_adapter_session(
            session_id,
            cwd,
            limit,
            offset,
            agent_hints=agent_hints or None,
        )
        if adapter_data is not None:
            return unwrap(json.dumps({"ok": True, "data": adapter_data}))
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
