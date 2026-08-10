"""Task-store and board_os Scrumban cos_* tools."""

from __future__ import annotations

import sys
from pathlib import Path

from _server_runtime import _db_conn, _detect_agent_session_default, logger, mcp
from database import get_pooled_conn
from tools._shared import fail, ok, safe_tool
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
# Board-OS MCP tools — Scrumban task board
# ---------------------------------------------------------------------------
# Imported from core/board_os/mcp_tools.py. Each tool here is a thin
# @mcp.tool-decorated wrapper that injects the server's shared _db_conn.

try:
    # `from board_os...` requires the project root (parent of `core/`)
    # on sys.path, since `core/` is a namespace package without __init__.py.
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))
    from board_os import mcp_tools as _board_mcp  # type: ignore

    _BOARD_OS_AVAILABLE = True
except ImportError as _exc:
    logger.warning("board_os MCP tools unavailable: %s", _exc)
    _BOARD_OS_AVAILABLE = False


if _BOARD_OS_AVAILABLE:

    @mcp.tool(
        name="cos_task_create",
        annotations={
            "title": "Create New Scrumban Task",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": False,
        },
    )
    def cos_task_create(
        title: str,
        swimlane: str,
        kind: str,
        priority: str = "P2",
        appetite: str = "1d",
        epic: str = "",
        labels: list[str] | None = None,
        outcome: str = "",
        acceptance: str = "",
        repro: str = "",
        read_first: list[str] | None = None,
        depends_on: list[str] | None = None,
        status: str = "icebox",
        ready: bool = False,
        agent_session: str = "",
    ) -> str:
        """Create a new Scrumban task file + sync to DB.

        Prefer this over hand-writing YAML. Validates swimlane against
        scrumban-config.yaml and kind against the 8-value enum. Pass
        ready=True to mark the task pullable in one shot; for bug-kind
        tasks pass acceptance= (G/W/T lines) and repro= so the create
        satisfies its own DoR in one call.
        """
        resolved_session = agent_session or _detect_agent_session_default() or None
        return _board_mcp.cos_task_create(
            get_pooled_conn(),
            title=title,
            swimlane=swimlane,
            kind=kind,
            priority=priority,
            appetite=appetite,
            epic=epic or None,
            labels=labels or [],
            outcome=outcome or None,
            acceptance=acceptance or None,
            repro=repro or None,
            read_first=read_first or [],
            depends_on=depends_on or [],
            status=status,
            ready=ready,
            agent_session=resolved_session,
        )

    @mcp.tool(
        name="cos_task_board",
        annotations={
            "title": "Scrumban Board State",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    def cos_task_board(
        swimlane: str = "",
        kind: str = "",
        epic: str = "",
        status_filter: list[str] | None = None,
        include_archive: bool = False,
        limit: int = 50,
        page_size: int = 50,
        cursor: str = "",
    ) -> str:
        """Return the board state grouped by (swimlane, status) with WIP info. Complete/archive columns are keyset-paginated (pass cursor + status_filter to load more)."""
        return _board_mcp.cos_task_board(
            get_pooled_conn(),
            swimlane=swimlane or None,
            kind=kind or None,
            epic=epic or None,
            status_filter=status_filter,
            include_archive=include_archive,
            limit=limit,
            page_size=page_size,
            cursor=cursor or None,
        )

    @mcp.tool(
        name="cos_task_show",
        annotations={
            "title": "Show Single Task (frontmatter + body)",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    def cos_task_show(task_id: str, include_body: bool = True) -> str:
        """Show a single task's frontmatter fields and full markdown body — in-session alternative to raw ls/grep/Read on docs/tasks."""
        return _board_mcp.cos_task_show(
            get_pooled_conn(),
            task_id=task_id,
            include_body=include_body,
        )

    @mcp.tool(
        name="cos_task_history",
        annotations={
            "title": "Task History (create + transitions + edits + commits)",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    def cos_task_history(task_id: str, include_commits: bool = True, limit: int = 200) -> str:
        """Full actor-attributed task history — creation, status transitions, field edits, and git commits."""
        return _board_mcp.cos_task_history(
            get_pooled_conn(),
            task_id=task_id,
            include_commits=include_commits,
            limit=limit,
        )

    @mcp.tool(
        name="cos_task_edit",
        annotations={
            "title": "Edit Task Fields / Body (actor-attributed)",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": False,
        },
    )
    def cos_task_edit(
        task_id: str,
        title: str = "",
        priority: str = "",
        swimlane: str = "",
        appetite: str = "",
        epic: str = "",
        labels_csv: str = "",
        body: str = "",
        actor_type: str = "agent",
        actor_id: str = "",
        source: str = "mcp",
    ) -> str:
        """Edit a task's frontmatter fields and/or body; each change is recorded to the actor-attributed edit history."""
        return _board_mcp.cos_task_edit(
            get_pooled_conn(),
            task_id=task_id,
            title=title or None,
            priority=priority or None,
            swimlane=swimlane or None,
            appetite=appetite or None,
            epic=epic or None,
            labels=[s.strip() for s in labels_csv.split(",") if s.strip()] if labels_csv else None,
            body=body or None,
            actor_type=actor_type,
            actor_id=actor_id or None,
            source=source,
        )

    @mcp.tool(
        name="cos_task_link",
        annotations={
            "title": "Link a Task to a Forge Issue/PR (external_ref)",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    def cos_task_link(task_id: str, ref: str) -> str:
        """Set a task's optional external_ref (e.g. github#42) — forge auto-detected; metadata only, never the id."""
        return _board_mcp.cos_task_link(get_pooled_conn(), task_id=task_id, ref=ref)

    @mcp.tool(
        name="cos_presence_query",
        annotations={
            "title": "Live Agent Presence (sessions + states)",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    def cos_presence_query(agent: str = "") -> str:
        """Return per-agent presence state and live-session inventory.

        Reads `.coding-os/<agent>/sessions/*.json` (the same files
        agent-presence.sh writes) and applies the SSOT rules in
        `board_os.presence`.  When `agent` is empty, every adapter
        registered in adapters/<id>/adapter.yaml is reported.

        Used by `cos daily`, CI gates, and the live-agents board UI to
        verify zombie sessions are gone after deploy.
        """
        try:
            from board_os.hub_adapter_manifest import list_agent_manifest_rows
            from board_os.presence import (
                agent_state as _agent_state_q,
                session_inventory as _session_inventory_q,
            )
        except ImportError as exc:
            return fail(
                "unavailable",
                f"board_os presence module not importable: {exc}",
                retryable=False,
            )

        # Resolve the project root the same way the web routes do so
        # multi-project servers inspect the right .coding-os/ tree.
        try:
            from web._project_context import current_project_root  # type: ignore

            root = current_project_root()
        except Exception as exc:
            return fail(
                "unavailable",
                f"cannot resolve project root: {exc}",
                retryable=False,
            )

        agents = (
            [agent.strip()]
            if agent.strip()
            else [str(r.get("id") or "") for r in list_agent_manifest_rows() if r.get("id")]
        )
        states: dict[str, str] = {}
        sessions: list[dict] = []
        for aid in agents:
            if not aid:
                continue
            d = root / ".coding-os" / aid / "sessions"
            states[aid] = _agent_state_q(d)
            sessions.extend(_session_inventory_q(aid, d))
        return ok(
            {
                "agent_states": states,
                "session_states": sessions,
                "session_counts": {
                    aid: sum(1 for s in sessions if s["agent"] == aid) for aid in agents
                },
                "scope": "per_project",
                "root": str(root),
            }
        )

    @mcp.tool(
        name="cos_task_move",
        annotations={
            "title": "Move Task to New Status",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": False,
        },
    )
    def cos_task_move(
        task_id: str,
        to: str,
        reason: str = "",
        bypass_wip: bool = False,
        agent_session: str = "",
    ) -> str:
        """Transition a task through the Scrumban state machine."""
        resolved_session = agent_session or _detect_agent_session_default() or None
        return _board_mcp.cos_task_move(
            get_pooled_conn(),
            task_id=task_id,
            to=to,
            reason=reason or "mcp:cos_task_move (no reason given)",
            bypass_wip=bypass_wip,
            agent_session=resolved_session,
        )

    @mcp.tool(
        name="cos_task_reposition",
        annotations={
            "title": "Reposition Task (status and/or swimlane)",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": False,
        },
    )
    def cos_task_reposition(
        task_id: str,
        swimlane: str = "",
        to: str = "",
        reason: str = "",
        bypass_wip: bool = False,
        agent_session: str = "",
    ) -> str:
        """Update Scrumban status and/or swimlane (MD frontmatter + sync)."""
        resolved_session = agent_session or _detect_agent_session_default() or None
        return _board_mcp.cos_task_reposition(
            get_pooled_conn(),
            task_id=task_id,
            swimlane=swimlane or None,
            to=to or None,
            reason=reason or None,
            bypass_wip=bypass_wip,
            agent_session=resolved_session,
        )

    @mcp.tool(
        name="cos_task_ready",
        annotations={
            "title": "Mark Task Ready (toggle pull-gate label)",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    def cos_task_ready(
        task_id: str,
        ready: bool = True,
        agent_session: str = "",
    ) -> str:
        """Add or remove the 'ready' label that gates icebox→in_progress."""
        resolved_session = agent_session or _detect_agent_session_default() or None
        return _board_mcp.cos_task_ready(
            get_pooled_conn(),
            task_id=task_id,
            ready=ready,
            agent_session=resolved_session,
        )

    @mcp.tool(
        name="cos_task_reclaim",
        annotations={
            "title": "Reclaim Zombie in_progress Tasks",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    def cos_task_reclaim(
        idle_hours: int = 0,
        dry_run: bool = False,
        agent_session: str = "",
    ) -> str:
        """Reclaim zombie in_progress tasks (idle + owner session inactive) to icebox+ready."""
        resolved_session = agent_session or _detect_agent_session_default() or None
        return _board_mcp.cos_task_reclaim(
            get_pooled_conn(),
            idle_hours=idle_hours or None,
            dry_run=dry_run,
            agent_session=resolved_session,
        )

    @mcp.tool(
        name="cos_task_reconcile",
        annotations={
            "title": "Reconcile Stranded Tasks (review-first)",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    def cos_task_reconcile(include_active: bool = False) -> str:
        """Triage stranded in_progress/testing tasks with completion evidence + a review recommendation (read-only)."""
        return _board_mcp.cos_task_reconcile(get_pooled_conn(), include_active=include_active)

    @mcp.tool(
        name="cos_task_pick",
        annotations={
            "title": "Pick Next Task to Work On",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    def cos_task_pick(
        swimlane: str = "",
        priority_min: str = "P2",
        max_candidates: int = 5,
    ) -> str:
        """Return top candidate tasks to start next, ranked by priority."""
        return _board_mcp.cos_task_pick(
            get_pooled_conn(),
            swimlane=swimlane or None,
            priority_min=priority_min,
            max_candidates=max_candidates,
        )

    @mcp.tool(
        name="cos_task_claim_next",
        annotations={
            "title": "Atomically Claim Next Runnable Task",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": False,
        },
    )
    def cos_task_claim_next(
        swimlane: str = "",
        priority_min: str = "P2",
        agent_session: str = "",
    ) -> str:
        """Atomically select+claim the top runnable task for this session (or claimed=null)."""
        return _board_mcp.cos_task_claim_next(
            get_pooled_conn(),
            swimlane=swimlane or None,
            priority_min=priority_min,
            agent_session=agent_session or None,
        )

    @mcp.tool(
        name="cos_task_daily",
        annotations={
            "title": "Daily Standup Summary",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    def cos_task_daily(since: str = "24h", agent_session: str = "") -> str:
        """Produce the daily standup summary."""
        return _board_mcp.cos_task_daily(
            get_pooled_conn(),
            since=since,
            agent_session=agent_session or None,
        )

    @mcp.tool(
        name="cos_task_retro",
        annotations={
            "title": "Weekly Retrospective",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    def cos_task_retro(since: str = "7d") -> str:
        """Weekly retro metrics (cycle time, throughput, emergency count)."""
        return _board_mcp.cos_task_retro(get_pooled_conn(), since=since)

    @mcp.tool(
        name="cos_task_wip_check",
        annotations={
            "title": "WIP Cap Health Check",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    def cos_task_wip_check() -> str:
        """Lightweight check of current WIP counts vs. configured caps."""
        return _board_mcp.cos_task_wip_check(get_pooled_conn())

    @mcp.tool(
        name="cos_work_log_append",
        annotations={
            "title": "Append Line to Task Work Log",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": False,
        },
    )
    def cos_work_log_append(
        task_id: str,
        summary: str,
        agent_session: str = "",
        source: str = "manual",
    ) -> str:
        """Append one Work Log line to a task. Critical for Codex sessions."""
        resolved_session = agent_session or _detect_agent_session_default() or None
        return _board_mcp.cos_work_log_append(
            get_pooled_conn(),
            task_id=task_id,
            summary=summary,
            agent_session=resolved_session,
            source=source,
        )
