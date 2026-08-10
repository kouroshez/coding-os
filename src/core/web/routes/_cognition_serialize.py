"""Wire format for cognition chat: SDK objects to JSON-safe dicts and SSE frames.

Leaf module — it knows the SDK's block shapes and nothing about routing, so a
change to how a message is rendered never touches the request handlers.
"""

from __future__ import annotations

import dataclasses
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


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
