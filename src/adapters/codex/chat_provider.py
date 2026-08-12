"""Codex Hub transcript provider backed by the official Python SDK."""

from __future__ import annotations

import asyncio
import logging
import os
import re
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, TypeVar

logger = logging.getLogger("coding_os.chat.codex")

_CLIENT: Any = None
_CLIENT_LOCK = asyncio.Lock()
_T = TypeVar("_T")

_SDK_PACKAGE = "openai-codex"
_MODEL_RE = re.compile(r'^\s*model\s*=\s*["\']([^"\']+)["\']\s*$')


def available() -> bool:
    try:
        import openai_codex  # noqa: F401
    except ImportError:
        return False
    return True


def requirement() -> dict[str, str]:
    """What is missing for this provider to run, and the command that supplies it."""
    if available():
        return {}
    return {
        "missing": f"the {_SDK_PACKAGE} package",
        "remedy": f"uv pip install '{_SDK_PACKAGE}>=0.144.4,<0.145.0'",
    }


def _config_path() -> Path:
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "config.toml"


def discovered_models() -> list[dict[str, str]]:
    """The model Codex is configured to use, read from the user's own config.

    Codex accepts a freeform `-m <MODEL>`; neither the CLI nor the SDK publishes a
    catalog to enumerate. The one model ID we can state without inventing it is the
    one the user already wrote down, so an empty config yields an empty list rather
    than a plausible guess.
    """
    path = _config_path()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lines:
        if line.lstrip().startswith("["):
            break  # past the top-level table; profile models are not the active one
        match = _MODEL_RE.match(line)
        if match:
            model = match.group(1)
            return [{"id": model, "label": model, "default": True, "source": str(path)}]
    return []


async def _with_client(call: Callable[[Any], Awaitable[_T]]) -> _T:
    global _CLIENT
    async with _CLIENT_LOCK:
        if _CLIENT is None:
            from openai_codex import AsyncCodex

            _CLIENT = AsyncCodex()
        try:
            return await call(_CLIENT)
        except Exception:
            try:
                await _CLIENT.close()
            except Exception as exc:
                logger.debug("Codex chat client close failed: %s", exc)
            _CLIENT = None
            raise


def _jsonable(value: Any) -> Any:
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        return dump(mode="json", by_alias=True)
    root = getattr(value, "root", None)
    if root is not None:
        return _jsonable(root)
    if hasattr(value, "value"):
        return value.value
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return value


def _session(thread: Any) -> dict[str, Any]:
    git_info = getattr(thread, "git_info", None)
    cwd = _jsonable(getattr(thread, "cwd", None))
    return {
        "session_id": thread.id,
        "summary": None,
        "custom_title": getattr(thread, "name", None),
        "first_prompt": (getattr(thread, "preview", None) or "")[:400] or None,
        "last_modified": int(getattr(thread, "updated_at", 0) or 0) * 1000 or None,
        "file_size": None,
        "git_branch": getattr(git_info, "branch", None),
        "cwd": str(cwd) if cwd else None,
        "tag": None,
        "created_at": int(getattr(thread, "created_at", 0) or 0) * 1000 or None,
        "agent": "codex",
        "writable": False,
        "source": _jsonable(getattr(thread, "source", None)),
        "status": _jsonable(getattr(thread, "status", None)),
        "model_provider": getattr(thread, "model_provider", None),
    }


def _message(
    session_id: str,
    item_id: str | None,
    role: str,
    blocks: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "uuid": item_id,
        "session_id": session_id,
        "type": role,
        "role": role,
        "model": None,
        "stop_reason": None,
        "usage": None,
        "blocks": blocks,
        "parent_tool_use_id": None,
    }


def _user_blocks(content: list[Any]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for wrapped in content:
        item = getattr(wrapped, "root", wrapped)
        item_type = getattr(item, "type", "")
        if item_type == "text":
            blocks.append({"type": "text", "text": item.text})
        elif item_type in {"image", "localImage"}:
            target = getattr(item, "url", None) or getattr(item, "path", None) or "image"
            blocks.append({"type": "text", "text": f"[image: {target}]"})
        elif item_type in {"skill", "mention"}:
            blocks.append({"type": "text", "text": f"${getattr(item, 'name', item_type)}"})
    return blocks


def _tool_messages(session_id: str, item: Any) -> list[dict[str, Any]]:
    item_type = getattr(item, "type", "")
    item_id = getattr(item, "id", None)
    if item_type == "commandExecution":
        name = "Bash"
        arguments = {"command": getattr(item, "command", "")}
        output = getattr(item, "aggregated_output", None)
        failed = getattr(item, "exit_code", 0) not in (None, 0)
    elif item_type == "mcpToolCall":
        name = f"{getattr(item, 'server', 'mcp')}:{getattr(item, 'tool', 'tool')}"
        arguments = _jsonable(getattr(item, "arguments", None))
        output = _jsonable(getattr(item, "result", None) or getattr(item, "error", None))
        failed = getattr(item, "error", None) is not None
    elif item_type == "dynamicToolCall":
        name = getattr(item, "tool", "tool")
        arguments = _jsonable(getattr(item, "arguments", None))
        output = _jsonable(getattr(item, "content_items", None))
        failed = getattr(item, "success", None) is False
    else:
        return []
    use_id = item_id or f"tool-{len(str(arguments))}"
    return [
        _message(
            session_id,
            item_id,
            "assistant",
            [{"type": "tool_use", "id": use_id, "name": name, "input": arguments}],
        ),
        _message(
            session_id,
            f"{use_id}-result",
            "user",
            [
                {
                    "type": "tool_result",
                    "tool_use_id": use_id,
                    "content": "" if output is None else str(output),
                    "is_error": failed,
                }
            ],
        ),
    ]


def _messages(thread: Any) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for turn in getattr(thread, "turns", []):
        for wrapped in getattr(turn, "items", []):
            item = getattr(wrapped, "root", wrapped)
            item_type = getattr(item, "type", "")
            item_id = getattr(item, "id", None)
            if item_type == "userMessage":
                blocks = _user_blocks(getattr(item, "content", []))
                if blocks:
                    messages.append(_message(thread.id, item_id, "user", blocks))
            elif item_type == "agentMessage":
                text = getattr(item, "text", "")
                if text:
                    messages.append(
                        _message(thread.id, item_id, "assistant", [{"type": "text", "text": text}])
                    )
            elif item_type == "reasoning":
                parts = getattr(item, "summary", None) or getattr(item, "content", None) or []
                text = "\n\n".join(str(part) for part in parts if part)
                if text:
                    messages.append(
                        _message(
                            thread.id,
                            item_id,
                            "assistant",
                            [{"type": "thinking", "text": text}],
                        )
                    )
            else:
                messages.extend(_tool_messages(thread.id, item))
    return messages


async def list_sessions(cwd: str, limit: int) -> list[dict[str, Any]]:
    async def call(client: Any) -> Any:
        return await client.thread_list(cwd=cwd, limit=limit, archived=False)

    response = await _with_client(call)
    return [_session(thread) for thread in response.data]


async def get_session(
    session_id: str,
    cwd: str,
    limit: int,
    offset: int,
) -> dict[str, Any] | None:
    async def call(client: Any) -> Any:
        from openai_codex import AsyncThread

        return await AsyncThread(client, session_id).read(include_turns=True)

    try:
        response = await _with_client(call)
    except Exception as exc:
        message = str(exc).lower()
        if "not found" in message or "no rollout found" in message:
            return None
        raise
    thread = response.thread
    if _jsonable(getattr(thread, "cwd", None)) != cwd:
        return None
    messages = _messages(thread)
    page = messages[offset : offset + limit]
    return {
        "session": _session(thread),
        "messages": page,
        "count": len(page),
        "offset": offset,
        "meta": {"layer": "cognition", "source": "codex_sdk", "agent": "codex"},
    }
