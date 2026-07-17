"""
Thinking OS — MCP metrics tools (TASK-143).

3 tools for agent/model performance tracking:
  - cos_metric_record: INSERT a new metric row
  - cos_metric_query: filtered query with pagination
  - cos_metric_trend: aggregated success rate trends
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Optional

logger = logging.getLogger("thinking_os.metrics")

# Whitelisted values for validation
VALID_OUTCOMES = {"success", "rework", "partial", "blocked"}
VALID_GROUP_BY = {"domain", "model", "agent_type", "complexity"}
VALID_METRICS = {"success_rate", "rework_rate", "count", "time_to_solution"}


# ---------------------------------------------------------------------------
# cos_metric_record
# ---------------------------------------------------------------------------


def metric_record(
    conn: sqlite3.Connection,
    *,
    task_id: str | None = None,
    agent_type: str,
    model: str | None = None,
    duration_ms: int | None = None,
    outcome: str,
    domain: str | None = None,
    complexity: str | None = None,
) -> dict:
    """Record a single agent metric.

    Args:
        conn: SQLite connection.
        task_id: Task identifier (e.g. "TASK-143").
        agent_type: Type of agent (e.g. "general", "planner").
        model: Model used (e.g. "sonnet", "opus").
        duration_ms: Duration in milliseconds (self-reported).
        outcome: One of: success, rework, partial, blocked.
        domain: Task domain (e.g. "BACKEND", "FRONTEND").
        complexity: Cynefin classification (e.g. "CLEAR", "COMPLICATED").

    Returns:
        Dict with id of the inserted row and confirmation.
    """
    if outcome not in VALID_OUTCOMES:
        return {"error": f"Invalid outcome '{outcome}'. Must be one of: {sorted(VALID_OUTCOMES)}"}

    cursor = conn.execute(
        "INSERT INTO agent_metrics (task_id, agent_type, model, duration_ms, outcome, domain, complexity) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (task_id, agent_type, model, duration_ms, outcome, domain, complexity),
    )
    conn.commit()
    return {"id": cursor.lastrowid, "status": "recorded"}


# ---------------------------------------------------------------------------
# cos_metric_query
# ---------------------------------------------------------------------------


def metric_query(
    conn: sqlite3.Connection,
    *,
    domain: str | None = None,
    model: str | None = None,
    outcome: str | None = None,
    agent_type: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 20,
) -> dict:
    """Query agent metrics with optional filters.

    Args:
        conn: SQLite connection.
        domain: Filter by domain.
        model: Filter by model.
        outcome: Filter by outcome.
        agent_type: Filter by agent type.
        date_from: ISO date string (inclusive).
        date_to: ISO date string (inclusive).
        limit: Max rows to return (1-100, default 20).

    Returns:
        Dict with rows list and total count.
    """
    limit = max(1, min(100, limit))
    conditions: list[str] = []
    params: list = []

    if domain is not None:
        conditions.append("domain = ?")
        params.append(domain)
    if model is not None:
        conditions.append("model = ?")
        params.append(model)
    if outcome is not None:
        conditions.append("outcome = ?")
        params.append(outcome)
    if agent_type is not None:
        conditions.append("agent_type = ?")
        params.append(agent_type)
    if date_from is not None:
        conditions.append("created_at >= ?")
        params.append(date_from)
    if date_to is not None:
        conditions.append("created_at <= ?")
        params.append(date_to + " 23:59:59")

    where = " AND ".join(conditions) if conditions else "1=1"

    count_row = conn.execute(f"SELECT COUNT(*) FROM agent_metrics WHERE {where}", params).fetchone()
    total = count_row[0]

    rows = conn.execute(
        f"SELECT id, task_id, agent_type, model, duration_ms, outcome, domain, complexity, created_at "
        f"FROM agent_metrics WHERE {where} ORDER BY created_at DESC LIMIT ?",
        params + [limit],
    ).fetchall()

    return {
        "total": total,
        "count": len(rows),
        "rows": [dict(row) for row in rows],
    }


# ---------------------------------------------------------------------------
# cos_metric_trend
# ---------------------------------------------------------------------------


def metric_trend(
    conn: sqlite3.Connection,
    *,
    metric: str = "success_rate",
    window_days: int = 30,
    group_by: str = "domain",
) -> dict:
    """Return aggregated trend data for a metric.

    Args:
        conn: SQLite connection.
        metric: One of: success_rate, rework_rate, count, time_to_solution.
        window_days: Lookback window in days (1-365, default 30).
        group_by: Group dimension: domain, model, agent_type, complexity.

    Returns:
        Dict with trends list.
    """
    if metric not in VALID_METRICS:
        return {"error": f"Invalid metric '{metric}'. Must be one of: {sorted(VALID_METRICS)}"}
    if group_by not in VALID_GROUP_BY:
        return {"error": f"Invalid group_by '{group_by}'. Must be one of: {sorted(VALID_GROUP_BY)}"}

    window_days = max(1, min(365, window_days))

    # Build aggregation query — group_by is validated against whitelist above
    sql = (
        f"SELECT {group_by} AS group_key, "
        "strftime('%Y-%W', created_at) AS period, "
        "SUM(CASE WHEN outcome = 'success' THEN 1 ELSE 0 END) AS success_count, "
        "SUM(CASE WHEN outcome = 'rework' THEN 1 ELSE 0 END) AS rework_count, "
        "AVG(NULLIF(duration_ms, 0)) AS avg_duration_ms, "
        "COUNT(*) AS total_count "
        "FROM agent_metrics "
        "WHERE created_at >= date('now', '-' || ? || ' days') "
        f"GROUP BY {group_by}, period "
        "ORDER BY period DESC, group_key"
    )

    rows = conn.execute(sql, (window_days,)).fetchall()

    trends = []
    for row in rows:
        entry = dict(row)
        total = entry["total_count"]
        if metric == "success_rate":
            entry["rate"] = round(entry["success_count"] / total, 2) if total > 0 else 0.0
        elif metric == "rework_rate":
            entry["rate"] = round(entry["rework_count"] / total, 2) if total > 0 else 0.0
        elif metric == "count":
            entry["rate"] = total
        elif metric == "time_to_solution":
            # Average wall-clock seconds per session; 0-duration sessions excluded.
            entry["rate"] = round((entry["avg_duration_ms"] or 0) / 1000.0, 1)
        trends.append(entry)

    return {"metric": metric, "window_days": window_days, "group_by": group_by, "trends": trends}
