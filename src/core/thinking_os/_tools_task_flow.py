"""Scrumban lifecycle — the cos_task_* transition, claim and reporting surface.

Thin @mcp.tool wrappers over board_os.mcp_tools that inject the server's
shared pooled connection. Record creation and board views live in
_tools_task_records.
"""

from __future__ import annotations

from _board_bridge import _BOARD_OS_AVAILABLE, _board_mcp
from _server_runtime import _detect_agent_session_default, mcp
from database import get_pooled_conn

if _BOARD_OS_AVAILABLE:

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
