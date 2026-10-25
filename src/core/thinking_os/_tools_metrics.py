"""Metric and log-query cos_* tools registered on the shared server."""

from __future__ import annotations

from _server_runtime import (
    _db_conn,
    mcp,
)
from tools._shared import ok, safe_tool
from tools.logs import log_query


# ---------------------------------------------------------------------------
# Metrics tools
# ---------------------------------------------------------------------------
@mcp.tool(
    name="cos_log_query",
    annotations={
        "title": "Query Durable Error / Log Store",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
@safe_tool
def cos_log_query(
    level: str = "",
    scope: str = "",
    since: str = "",
    search: str = "",
    session_id: str = "",
    trace_id: str = "",
    fingerprint: str = "",
    limit: int = 50,
) -> str:
    """Query the durable log_events store (WARN+), most-recent first — the agent's "what is broken now"."""
    result = log_query(
        _db_conn,
        level=level or None,
        scope=scope or None,
        since=since or None,
        search=search or None,
        session_id=session_id or None,
        trace_id=trace_id or None,
        fingerprint=fingerprint or None,
        limit=limit,
    )
    return ok(result, meta={"layer": "logs", "source": "cos_log_query"})


# ---------------------------------------------------------------------------
# Memory tools
