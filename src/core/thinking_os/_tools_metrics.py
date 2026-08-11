"""Metric and log-query cos_* tools registered on the shared server."""

from __future__ import annotations

from _server_runtime import (
    _db_conn,
    mcp,
)
from tools._shared import ok, safe_tool
from tools.logs import log_query
from tools.metrics import metric_query, metric_record, metric_trend


# ---------------------------------------------------------------------------
# Metrics tools
# ---------------------------------------------------------------------------
@mcp.tool(
    name="cos_metric_record",
    annotations={
        "title": "Record Agent Metric",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
@safe_tool
def cos_metric_record(
    agent_type: str,
    outcome: str,
    task_id: str = "",
    model: str = "",
    duration_ms: int = 0,
    domain: str = "",
    complexity: str = "",
) -> str:
    """Record a single agent performance metric after task completion.

    Args:
        agent_type: Type of agent (e.g. "general", "planner", "code-reviewer").
        outcome: Result — one of: success, rework, partial, blocked.
        task_id: Task identifier (e.g. "TASK-143"). Optional.
        model: Model used (e.g. "sonnet", "opus"). Optional.
        duration_ms: Duration in milliseconds. Optional.
        domain: Task domain (e.g. "BACKEND", "FRONTEND", "INFRA"). Optional.
        complexity: Cynefin classification (e.g. "CLEAR", "COMPLICATED"). Optional.

    Returns:
        str: JSON with inserted row id and status.
    """
    result = metric_record(
        _db_conn,
        task_id=task_id or None,
        agent_type=agent_type,
        model=model or None,
        duration_ms=duration_ms or None,
        outcome=outcome,
        domain=domain or None,
        complexity=complexity or None,
    )
    return ok(result, meta={"layer": "metrics"})


@mcp.tool(
    name="cos_metric_query",
    annotations={
        "title": "Query Agent Metrics",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
@safe_tool
def cos_metric_query(
    domain: str = "",
    model: str = "",
    outcome: str = "",
    agent_type: str = "",
    date_from: str = "",
    date_to: str = "",
    limit: int = 20,
) -> str:
    """Query agent metrics with optional filters.

    Args:
        domain: Filter by domain (e.g. "BACKEND"). Optional.
        model: Filter by model (e.g. "sonnet"). Optional.
        outcome: Filter by outcome (e.g. "rework"). Optional.
        agent_type: Filter by agent type. Optional.
        date_from: Start date (ISO format, e.g. "2026-03-01"). Optional.
        date_to: End date (ISO format, e.g. "2026-03-25"). Optional.
        limit: Max rows (1-100, default 20).

    Returns:
        str: JSON with total count and matching rows.
    """
    result = metric_query(
        _db_conn,
        domain=domain or None,
        model=model or None,
        outcome=outcome or None,
        agent_type=agent_type or None,
        date_from=date_from or None,
        date_to=date_to or None,
        limit=limit,
    )
    return ok(
        result,
        meta={
            "layer": "metrics",
            "filters_applied": {
                "domain": domain or None,
                "model": model or None,
                "outcome": outcome or None,
                "agent_type": agent_type or None,
            },
        },
    )


@mcp.tool(
    name="cos_metric_trend",
    annotations={
        "title": "Agent Metric Trends",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
@safe_tool
def cos_metric_trend(
    metric: str = "success_rate",
    window_days: int = 30,
    group_by: str = "domain",
) -> str:
    """Get aggregated trend data for agent metrics.

    Args:
        metric: One of: success_rate, rework_rate, count.
        window_days: Lookback window in days (1-365, default 30).
        group_by: Grouping dimension: domain, model, agent_type, complexity.

    Returns:
        str: JSON with trends array containing period, counts, and rate.
    """
    result = metric_trend(
        _db_conn,
        metric=metric,
        window_days=window_days,
        group_by=group_by,
    )
    return ok(result, meta={"layer": "metrics"})


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
