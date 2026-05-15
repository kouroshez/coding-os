from __future__ import annotations

import json
from typing import Any

from .config import scope_width

EMOJI: dict[str, str] = {
    "DEBUG": "🔍",
    "INFO": "ℹ️ ",
    "OK": "✅",
    "WARN": "⚠️ ",
    "ERROR": "❌",
    "FATAL": "💀",
}

COLOR: dict[str, str] = {
    "DEBUG": "\x1b[90m",
    "INFO": "\x1b[36m",
    "OK": "\x1b[32m",
    "WARN": "\x1b[33m",
    "ERROR": "\x1b[31m",
    "FATAL": "\x1b[1;31m",
}

RESET = "\x1b[0m"


def _format_kv(kv: dict[str, Any]) -> str:
    if not kv:
        return ""
    parts = []
    for key, value in kv.items():
        text = str(value)
        if " " in text or "=" in text:
            text = json.dumps(text, ensure_ascii=False)
        parts.append(f"{key}={text}")
    return " ".join(parts)


def render_pretty(event: dict[str, Any]) -> str:
    lvl = event["lvl"]
    emoji = EMOJI.get(lvl, "  ")
    color = COLOR.get(lvl, "")
    short_ts = event["ts"][11:19]
    scope = event["scope"].ljust(scope_width())
    kv_text = _format_kv(event.get("kv") or {})
    body = event["msg"] if not kv_text else f"{event['msg']}  {kv_text}"
    return f"{emoji}  {short_ts}  {color}{lvl:<5}{RESET}  {scope}  {body}"


def render_short(event: dict[str, Any]) -> str:
    lvl = event["lvl"]
    short_ts = event["ts"][11:19]
    kv_text = _format_kv(event.get("kv") or {})
    body = event["msg"] if not kv_text else f"{event['msg']} {kv_text}"
    return f"{short_ts} {lvl:<5} {event['scope']} {body}"


def render_json(event: dict[str, Any]) -> str:
    payload: dict[str, Any] = {
        "ts": event["ts"],
        "lvl": event["lvl"],
        "scope": event["scope"],
        "msg": event["msg"],
    }
    for key, value in (event.get("kv") or {}).items():
        if key in payload:
            continue
        payload[key] = value
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


RENDERERS = {
    "pretty": render_pretty,
    "short": render_short,
    "json": render_json,
}


def render(mode: str, event: dict[str, Any]) -> str:
    renderer = RENDERERS.get(mode, render_short)
    return renderer(event)
