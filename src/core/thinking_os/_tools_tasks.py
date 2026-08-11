"""Task-store and board_os Scrumban cos_* tools."""

from __future__ import annotations

from _server_runtime import _db_conn, mcp
from tools._shared import ok, safe_tool
from tools.retrieve import log_retrieval, log_router_decision
from tools.tasks import task_by_filter, task_dependencies, task_dependents, task_search


# ---------------------------------------------------------------------------
# Task store tools
# ---------------------------------------------------------------------------
@mcp.tool(
    name="cos_task_search",
    annotations={
        "title": "Search Tasks (Semantic + Filter)",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
@safe_tool
def cos_task_search(
    query: str,
    status: str = "",
    domain: str = "",
    limit: int = 10,
) -> str:
    """Semantic search over the task store with optional status/domain filters.

    Use this when you need to find tasks related to a concept — even when
    exact keywords don't match. Falls back to LIKE on title + goal when
    embeddings are unavailable.

    Args:
        query: Natural language query (e.g. "payment splitting multi vendor").
        status: Optional status filter — one of open/wip/done/blocked. Empty = all.
        domain: Optional domain filter (BACKEND/FRONTEND/DOCS/INFRA/...). Empty = all.
        limit: Maximum results (1-100, default 10).

    Returns:
        JSON with results and count. Each result: task_id, title, domain,
        status, file_path, goal_text, dependencies, score.
    """
    results = task_search(
        _db_conn,
        query=query,
        status=status or None,
        domain=domain or None,
        limit=limit,
    )
    rids = log_retrieval(_db_conn, layer="tasks", query=query, rows=results)
    log_router_decision(
        _db_conn, query=query, chosen_layer="tasks", bytes_returned=len(str(results))
    )
    return ok(
        {"results": results, "count": len(results), "retrieval_ids": rids},
        meta={
            "layer": "tasks",
            "query": query,
            "filters_applied": {"status": status or None, "domain": domain or None},
        },
    )


@mcp.tool(
    name="cos_task_dependencies",
    annotations={
        "title": "Task Dependencies (Upstream)",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
@safe_tool
def cos_task_dependencies(task_id: str) -> str:
    """Return the tasks that `task_id` directly depends on.

    Use before starting a task to verify prerequisites are done. Returns
    only direct (first-level) dependencies — use repeated calls for
    transitive traversal.

    Args:
        task_id: Task identifier (e.g. "TASK-199").

    Returns:
        JSON with task_id, dependencies list, and count.
    """
    results = task_dependencies(_db_conn, task_id)
    return ok(
        {"task_id": task_id, "dependencies": results, "count": len(results)},
        meta={"layer": "tasks"},
    )


@mcp.tool(
    name="cos_task_dependents",
    annotations={
        "title": "Task Dependents (Downstream)",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
@safe_tool
def cos_task_dependents(task_id: str) -> str:
    """Return the tasks that declare `task_id` as a dependency.

    Use for impact analysis: "If I change TASK-195, what downstream tasks
    need to be re-verified?" Returns only direct dependents — non-transitive.

    Args:
        task_id: Task identifier (e.g. "TASK-195").

    Returns:
        JSON with task_id, dependents list, and count.
    """
    results = task_dependents(_db_conn, task_id)
    return ok(
        {"task_id": task_id, "dependents": results, "count": len(results)}, meta={"layer": "tasks"}
    )


@mcp.tool(
    name="cos_task_by_filter",
    annotations={
        "title": "List Tasks by Filter",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
@safe_tool
def cos_task_by_filter(
    status: str = "",
    domain: str = "",
    limit: int = 20,
) -> str:
    """List tasks matching an optional status and/or domain filter.

    No semantic query — pure structured filter. Use when you need "all
    open backend tasks" or "all blocked tasks" without a specific concept.

    Args:
        status: Filter by status (open/wip/done/blocked). Empty = all.
        domain: Filter by domain (BACKEND/FRONTEND/DOCS/...). Empty = all.
        limit: Maximum results (1-100, default 20).

    Returns:
        JSON with results list (sorted by task_id ASC) and count.
    """
    results = task_by_filter(
        _db_conn,
        status=status or None,
        domain=domain or None,
        limit=limit,
    )
    return ok(
        {"results": results, "count": len(results)},
        meta={
            "layer": "tasks",
            "filters_applied": {"status": status or None, "domain": domain or None},
        },
    )


# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Board-OS MCP tools — Scrumban task board
# ---------------------------------------------------------------------------
# Imported from core/board_os/mcp_tools.py. Each tool there is a thin
# @mcp.tool-decorated wrapper that injects the server's shared _db_conn.
# Imported for their registration side effect, in the order the registry
# has always carried them.
import _tools_task_records  # noqa: E402, F401  # isort: skip
import _tools_task_flow  # noqa: E402, F401  # isort: skip
