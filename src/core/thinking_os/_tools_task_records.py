"""Scrumban task records + board views — the cos_task_* create/read surface.

Thin @mcp.tool wrappers over board_os.mcp_tools that inject the server's
shared pooled connection. Status transitions live in _tools_task_flow.
"""

from __future__ import annotations

from _board_bridge import _BOARD_OS_AVAILABLE, _board_mcp
from _server_runtime import _detect_agent_session_default, mcp
from database import get_pooled_conn
from tools._shared import fail, ok

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
