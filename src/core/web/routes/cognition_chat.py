"""/api/cognition chat routes — sessions, roles, and the streaming send path.

Split from cognition.py because chat changes with the Claude SDK surface (block
shapes, session options, streaming) while traces and cost change with the
dispatcher's own telemetry. Both attach to the same router, so the URL surface
is byte-identical to before the split.

The SDK/adapter seam, the system prompts, and the transcript lookups moved to
leaf siblings; every name they own is re-exported below, so the helpers a test
patches on this module are still the ones these routes call.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

from fastapi import Body, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from .._deps import make_metrics_dep, make_rate_limit_dep
from .._envelope import unwrap
from . import cognition as _cog
from ._cognition_base import router
from ._cognition_chat_lookup import (
    _dispatch_transcript_chat as _dispatch_transcript_chat,
    _session_agent_hints as _session_agent_hints,
)
from ._cognition_chat_prompts import (
    _CHAT_SYSTEM as _CHAT_SYSTEM,
    _chat_system_prompt as _chat_system_prompt,
    _prime_with_project_description as _prime_with_project_description,
    _role_meta as _role_meta,
    _role_names as _role_names,
    _role_system_prompt as _role_system_prompt,
)
from ._cognition_chat_sdk import (
    _adapter_dispatcher as _adapter_dispatcher,
    _build_agent_options as _build_agent_options,
    _chat_presence_write as _chat_presence_write,
    _chat_session_options as _chat_session_options,
    _claude_sdk as _claude_sdk,
    _project_cwd as _project_cwd,
    _session_options_builder as _session_options_builder,
)
from ._cognition_serialize import (  # noqa: F401 — re-exported for the facade
    _coerce_block,
    _safe_serialize,
    _serialize_message,
    _serialize_session_info,
    _sse_chunk,
)

logger = logging.getLogger(__name__)

_CORE_DIR = Path(__file__).resolve().parents[3]
if str(_CORE_DIR) not in sys.path:
    sys.path.insert(0, str(_CORE_DIR))


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
        return unwrap(_cog._unavailable("no chat transcript provider is available"))
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


@router.get("/roles")
def list_roles(
    _rl=Depends(make_rate_limit_dep("cognition.roles")),
    _m=Depends(make_metrics_dep("cognition.roles")),
):
    """List the semantic roles a chat session can adopt (producer: thinking_os/agents/*.md)."""
    agents_dir = Path(__file__).resolve().parents[2] / "thinking_os" / "agents"
    roles = _role_names(agents_dir)
    return unwrap(
        json.dumps(
            {
                "ok": True,
                # `roles` stays a plain id list for existing consumers; `details`
                # carries the title and chain order the pickers render.
                "data": {
                    "roles": roles,
                    "details": _role_meta(agents_dir),
                    "count": len(roles),
                    "meta": {"layer": "cognition"},
                },
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
        return unwrap(_cog._unavailable("claude_agent_sdk not installed"))

    import secrets
    import time as _time

    model = body.get("model") or None
    routing_decision: dict | None = None
    if model == "auto":
        routing_decision = _cog._auto_route_model(prompt)
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
        return unwrap(_cog._unavailable("claude_agent_sdk not installed"))

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
