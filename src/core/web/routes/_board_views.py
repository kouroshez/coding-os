"""core.web.routes._board_views — whole-board and aggregate reads (list, config, standup)."""

from __future__ import annotations

import json

from fastapi import Depends, Query
from fastapi.responses import JSONResponse

from .._deps import make_metrics_dep, make_rate_limit_dep
from .._envelope import unwrap
from ._board_presence import (
    _ACTIVE_WINDOW_SECS,
    _agent_state,
    _presence_files,
    _session_inventory,
)
from ._board_shared import _board_tools, _db_conn, _unavailable, logger, router


@router.get("/list")
def board_list(
    swimlane: str | None = Query(None),
    kind: str | None = Query(None),
    epic: str | None = Query(None),
    include_archive: bool = Query(False),
    limit: int = Query(500),
    status: str | None = Query(None),
    page_size: int = Query(50),
    cursor: str | None = Query(None),
    _rl=Depends(make_rate_limit_dep("board.list")),
    _m=Depends(make_metrics_dep("board.list")),
):
    """Return the board state grouped by (swimlane, status).

    Active columns return in full (capped); complete/archive are keyset-paged.
    A per-column "load more" passes `status=<complete|archive>&cursor=<next>`
    to fetch that column's next page (TASK-223).
    """
    bt = _board_tools()
    if bt is None:
        return unwrap(_unavailable())
    conn = _db_conn()
    try:
        result = bt.cos_task_board(
            conn,
            swimlane=swimlane,
            kind=kind,
            epic=epic,
            status_filter=[status] if status else None,
            include_archive=include_archive,
            limit=limit,
            page_size=page_size,
            cursor=cursor,
            # The browser is not token-limited, so skip the 32KB agent-context
            # slice. Safe now that every column is bounded per-column (active
            # capped, complete/archive keyset-paged) — no return-all.
            apply_budget=False,
        )
    finally:
        conn.close()

    env = json.loads(result)
    if not env.get("ok"):
        # Standard error envelope + category-mapped status code (TASK-399) —
        # never a 400 wrapping a partially-enriched raw envelope.
        return unwrap(env)
    if env.get("ok"):
        # agent_states is the new, richer shape: {agent: "active"|"present"|"offline"}.
        # active_agents preserves the v0.5 contract ("list of ids that are not
        # offline") so older UI builds keep working during the rollout.
        from board_os._agent_runtime import human_actor
        from board_os.hub_adapter_manifest import list_agent_manifest_rows

        adapter_rows = list_agent_manifest_rows()
        agent_ids = [str(r["id"]) for r in adapter_rows]
        human = human_actor()
        # Human operator is always considered present. Identity is resolved
        # (not hard-coded) so a future auth layer supplies the real user.
        states: dict[str, str] = {human["id"]: "active"}
        session_states: list[dict] = []
        session_counts: dict[str, int] = {}
        conn = _db_conn()
        try:
            for agent in agent_ids:
                states[agent] = _agent_state(conn, agent)
                inv = _session_inventory(agent)
                session_states.extend(inv)
                if inv:
                    session_counts[agent] = len(inv)
        finally:
            conn.close()
        env["data"]["agent_states"] = states
        env["data"]["active_agents"] = [a for a, st in states.items() if st != "offline"]
        # P2 — surface live sessions per agent so the UI can render
        # "Cl·3" badges and a session-detail tooltip instead of
        # collapsing N parallel sessions into one verdict.
        env["data"]["session_states"] = session_states
        env["data"]["session_counts"] = session_counts
        # T19.3 — surface dispatcher sub-session count so the live-agents
        # panel can show "Claude (+ N sub-agents)". Sub-sessions are written
        # by adapters/claude/sdk_dispatcher.py::_presence_write() with
        # session_id prefix `ses-claude-sdk-`.
        sub_counts: dict[str, int] = {}
        for agent in agent_ids:
            try:
                files = _presence_files(agent)
                count = 0
                import time as _time

                now = _time.time()
                for path in files:
                    if not path.stem.startswith(f"ses-{agent}-sdk-"):
                        continue
                    try:
                        data = json.loads(path.read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError):
                        continue
                    if data.get("ended_at") is not None:
                        continue
                    last_tool = data.get("last_tool_at") or 0
                    if isinstance(last_tool, int) and now - last_tool <= _ACTIVE_WINDOW_SECS:
                        count += 1
                if count:
                    sub_counts[agent] = count
            except Exception as exc:
                logger.debug("sub-session count failed for %s: %s", agent, exc)
        env["data"]["sub_session_counts"] = sub_counts
        human_row = {
            "id": human["id"],
            "label": human["label"],
            "glyph": (human["label"][:1] or "H").upper(),
            "color": "#16a34a",
            "session": human["id"],
        }
        # Synthetic actor for unattended kernel maintenance (nightly
        # auto-archive/reclaim, ses-system-*). In the manifest so stream
        # attribution stays data-driven; has no presence files, so the UI
        # keeps it out of the live-pill row and legend.
        system_row = {
            "id": "system",
            "label": "system",
            "glyph": "Sy",
            "color": "#64748b",
            "session": "ses-system",
        }
        env["data"]["agent_manifest"] = [*adapter_rows, human_row, system_row]
        env["data"]["presence_scope"] = "per_project"

    return JSONResponse(status_code=200, content=env)


@router.get("/config")
def board_config(
    _rl=Depends(make_rate_limit_dep("board.config")),
    _m=Depends(make_metrics_dep("board.config")),
):
    """Return scrumban-config swimlanes + WIP caps + status column ids for the SPA."""
    try:
        from board_os.config import STATUS_ENUM, load_config
    except ImportError:
        return JSONResponse(
            status_code=503,
            content={"error": {"category": "unavailable", "message": "board_os not importable"}},
        )
    from web._project_context import current_project_root

    project_root = current_project_root()
    try:
        cfg = load_config(project_root)
    except FileNotFoundError:
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "category": "unavailable",
                    "message": "scrumban-config.yaml not found — run `cos board-config --init`",
                },
            },
        )
    swimlanes = [
        {
            "id": sl.id,
            "label": sl.label,
            "color": sl.color,
            "accent": sl.effective_accent(),
            "description": sl.description,
        }
        for sl in cfg.swimlanes
    ]
    columns = [{"id": sid, "label": sid.replace("_", " ").upper()} for sid in STATUS_ENUM]
    return JSONResponse(
        status_code=200,
        content={
            "data": {
                "swimlanes": swimlanes,
                "columns": columns,
                "wip_limits": {
                    "in_progress": cfg.wip_limits.in_progress,
                    "testing": cfg.wip_limits.testing,
                    "emergency": cfg.wip_limits.emergency,
                },
            },
            "meta": {"layer": "tasks", "source": "web.board_config"},
        },
    )


@router.get("/daily")
def board_daily(
    since: str = Query("24h"),
    agent_session: str | None = Query(None),
    _rl=Depends(make_rate_limit_dep("board.daily")),
    _m=Depends(make_metrics_dep("board.daily")),
):
    """Daily standup summary."""
    bt = _board_tools()
    if bt is None:
        return unwrap(_unavailable())
    conn = _db_conn()
    try:
        result = bt.cos_task_daily(conn, since=since, agent_session=agent_session)
    finally:
        conn.close()
    return unwrap(result)


@router.get("/retro")
def board_retro(
    since: str = Query("7d"),
    _rl=Depends(make_rate_limit_dep("board.retro")),
    _m=Depends(make_metrics_dep("board.retro")),
):
    """Weekly retrospective metrics."""
    bt = _board_tools()
    if bt is None:
        return unwrap(_unavailable())
    conn = _db_conn()
    try:
        result = bt.cos_task_retro(conn, since=since)
    finally:
        conn.close()
    return unwrap(result)


@router.get("/wip")
def board_wip(
    _rl=Depends(make_rate_limit_dep("board.wip")),
    _m=Depends(make_metrics_dep("board.wip")),
):
    """WIP cap health check."""
    bt = _board_tools()
    if bt is None:
        return unwrap(_unavailable())
    conn = _db_conn()
    try:
        result = bt.cos_task_wip_check(conn)
    finally:
        conn.close()
    return unwrap(result)


@router.get("/pick")
def board_pick(
    swimlane: str | None = Query(None),
    priority_min: str = Query("P2"),
    max_candidates: int = Query(5),
    _rl=Depends(make_rate_limit_dep("board.pick")),
    _m=Depends(make_metrics_dep("board.pick")),
):
    """Top candidate tasks to start next."""
    bt = _board_tools()
    if bt is None:
        return unwrap(_unavailable())
    conn = _db_conn()
    try:
        result = bt.cos_task_pick(
            conn,
            swimlane=swimlane,
            priority_min=priority_min,
            max_candidates=max_candidates,
        )
    finally:
        conn.close()
    return unwrap(result)
