"""/api/cognition onboarding + task-authoring routes.

Split from cognition.py because onboarding changes with the first-run product
flow — which docs get written, which tools the agent may touch — not with the
dispatcher telemetry the rest of the module reports on.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

from fastapi import Body, Depends
from fastapi.responses import StreamingResponse

from .._deps import make_metrics_dep, make_rate_limit_dep
from .._envelope import unwrap
from . import cognition as _cog, cognition_chat as _chat
from ._cognition_base import router
from .cognition_chat import (
    _build_agent_options,
    _project_cwd,
    _role_system_prompt,
    _safe_serialize,
    _sse_chunk,
)

logger = logging.getLogger(__name__)

_CORE_DIR = Path(__file__).resolve().parents[3]
if str(_CORE_DIR) not in sys.path:
    sys.path.insert(0, str(_CORE_DIR))


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
    sdk = _chat._claude_sdk()
    if sdk is None:
        return unwrap(_cog._unavailable("claude_agent_sdk not installed"))

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
    state = _cog._state_dir()
    payload = _onboarding_state(project, state)
    payload["meta"] = {"layer": "cognition"}
    return unwrap(json.dumps({"ok": True, "data": payload}))


@router.post("/onboarding-status/dismiss")
def onboarding_dismiss(
    _rl=Depends(make_rate_limit_dep("cognition.onboarding_dismiss")),
    _m=Depends(make_metrics_dep("cognition.onboarding_dismiss")),
):
    """Persist the onboarding hero dismissal so it stops reappearing on reload."""
    state = _cog._state_dir()
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
    sdk = _chat._claude_sdk()
    if sdk is None:
        return unwrap(_cog._unavailable("claude_agent_sdk not installed"))

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
