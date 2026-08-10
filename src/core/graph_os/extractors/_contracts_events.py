"""Non-HTTP surface scanners — MCP tools, Celery, Django signals, websockets, pub/sub, SSE.

Grouped by what they are rather than by language: these are the surfaces a
service exposes without a URL, and they share the handles_event edge type.
"""

from __future__ import annotations

import re

from ._contracts_shared import (
    _STRING_CAPTURE,
    ContractMatch,
    _line_of,
    _next_def_name,
)

# MCP tool decorators: @mcp.tool("name"), @mcp.tool(name="x")
_MCP_TOOL_RE = re.compile(
    rf"""@(?P<server>[A-Za-z_][\w.]*)\.tool\s*\(\s*
        (?:name\s*=\s*)?{_STRING_CAPTURE}
    """,
    re.VERBOSE,
)
_MCP_SAFE_TOOL_RE = re.compile(r"@safe_tool\b")

# Celery / RQ / Channels / websockets.
_CELERY_TASK_RE = re.compile(
    rf"""@(?P<app>[A-Za-z_][\w.]*)\.task\s*(?:\([^)]*?name\s*=\s*{_STRING_CAPTURE}[^)]*\))?
        \s*\n\s*def\s+(?P<handler>[A-Za-z_][\w]*)
    """,
    re.VERBOSE,
)
_CHANNELS_RECEIVER_RE = re.compile(
    r"""@(?:receiver)\s*\(\s*[A-Za-z_][\w]*\s*,\s*sender\s*=\s*(?P<sender>[A-Za-z_][\w.]*)""",
    re.VERBOSE,
)
_WEBSOCKET_RE = re.compile(
    rf"""@(?P<app>[A-Za-z_][\w.]*)\.sock\.route\s*\(\s*{_STRING_CAPTURE}""",
    re.VERBOSE,
)

# R4: event-driven handler patterns — `@bus.on("event")`, `@router.subscribe`,
# `@<emitter>.subscribe`, FastAPI SSE endpoints, hook event subscribers.
# Captured kind="event" — flows into the same handles_event edge type.
_PUBSUB_ON_RE = re.compile(
    rf"""@(?P<emitter>[A-Za-z_][\w.]*)\.on\s*\(\s*{_STRING_CAPTURE}""",
    re.VERBOSE,
)
_PUBSUB_SUBSCRIBE_RE = re.compile(
    rf"""@(?P<emitter>[A-Za-z_][\w.]*)\.subscribe\s*\(\s*{_STRING_CAPTURE}""",
    re.VERBOSE,
)
# FastAPI/Starlette SSE: function returns EventSourceResponse(...) or
# yields ServerSentEvent(...) — best paired with an @app.get/@router.get
# decorator (already captured by FASTAPI_ROUTE_RE). Flag the function
# so the route node can be annotated; we promote the route from
# handles_route → handles_event via post-pass downstream.
_SSE_HINT_RE = re.compile(
    r"""(?:EventSourceResponse|ServerSentEvent|sse_starlette)\s*\(""",
    re.VERBOSE,
)


_MCP_NOISE_NAMES = {"name", "x", "y", "z", "foo", "bar", "tool", "test"}
_MCP_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{2,}$")


def _scan_mcp(content: str) -> list[ContractMatch]:
    hits: list[ContractMatch] = []
    for match in _MCP_TOOL_RE.finditer(content):
        name = (match.group("path") or "").strip()
        if name in _MCP_NOISE_NAMES or not _MCP_NAME_RE.match(name):
            continue
        hits.append(
            ContractMatch(
                kind="mcp",
                framework="mcp",
                method="rpc",
                path=name,
                handler=_next_def_name(content, match.end()),
                line=_line_of(content, match.start()),
            )
        )
    # Count @safe_tool decorators separately as a signal that this
    # module participates in the MCP envelope contract (Rule 14).
    if _MCP_SAFE_TOOL_RE.search(content):
        # Not a route on its own — no match emitted; callers use the
        # `@safe_tool` presence implicitly via the evidence audit.
        pass
    return hits


def _scan_celery(content: str) -> list[ContractMatch]:
    hits: list[ContractMatch] = []
    for match in _CELERY_TASK_RE.finditer(content):
        task_name = match.group("path") or match.group("handler")
        hits.append(
            ContractMatch(
                kind="event",
                framework="celery",
                method="task",
                path=task_name,
                handler=match.group("handler"),
                line=_line_of(content, match.start()),
            )
        )
    return hits


def _scan_channels_signals(content: str) -> list[ContractMatch]:
    hits: list[ContractMatch] = []
    for match in _CHANNELS_RECEIVER_RE.finditer(content):
        hits.append(
            ContractMatch(
                kind="event",
                framework="django_signals",
                method="signal",
                path=match.group("sender"),
                handler=None,
                line=_line_of(content, match.start()),
            )
        )
    return hits


def _scan_websocket(content: str) -> list[ContractMatch]:
    hits: list[ContractMatch] = []
    for match in _WEBSOCKET_RE.finditer(content):
        hits.append(
            ContractMatch(
                kind="websocket",
                framework="generic",
                method="ws",
                path=match.group("path"),
                handler=None,
                line=_line_of(content, match.start()),
            )
        )
    return hits


def _scan_pubsub(content: str, *, framework_label: str) -> list[ContractMatch]:
    """R4: collect `@bus.on(...)` / `@<emitter>.subscribe(...)` matches.

    framework_label tags the source language (`python` / `ts`).
    """
    hits: list[ContractMatch] = []
    for match in _PUBSUB_ON_RE.finditer(content):
        emitter = match.group("emitter")
        event_name = match.group("path")
        # Skip noisy matches: `app.on` (Flask before_request etc.) and
        # `os.on` are clearly not pubsub. Allow when emitter has a
        # discriminating suffix (bus/emitter/events).
        emitter_tail = emitter.split(".")[-1].lower()
        if emitter_tail not in {"bus", "events", "emitter", "pubsub", "signals"}:
            continue
        hits.append(
            ContractMatch(
                kind="event",
                framework=f"{framework_label}_{emitter_tail}",
                method="on",
                path=f"{emitter}:{event_name}",
                handler=None,
                line=_line_of(content, match.start()),
            )
        )
    for match in _PUBSUB_SUBSCRIBE_RE.finditer(content):
        emitter = match.group("emitter")
        event_name = match.group("path")
        hits.append(
            ContractMatch(
                kind="event",
                framework=f"{framework_label}_subscribe",
                method="subscribe",
                path=f"{emitter}:{event_name}",
                handler=None,
                line=_line_of(content, match.start()),
            )
        )
    return hits


def _scan_sse(content: str) -> list[ContractMatch]:
    """R4: FastAPI/Starlette SSE — file uses EventSourceResponse /
    ServerSentEvent. Emits one synthetic event match per file so trace
    knows the file participates in event flows."""
    hits: list[ContractMatch] = []
    m = _SSE_HINT_RE.search(content)
    if m:
        hits.append(
            ContractMatch(
                kind="event",
                framework="fastapi_sse",
                method="sse",
                path="<file_scope>",
                handler=None,
                line=_line_of(content, m.start()),
            )
        )
    return hits
