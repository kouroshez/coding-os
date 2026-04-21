"""core.web.routes.board — /api/board/* HTTP wrappers for cos_task_* tools.

PURPOSE: Expose Scrumban board operations (create/move/list/daily/retro/wip)
         as FastAPI endpoints so the SPA can render the board without MCP.
INPUT:   HTTP request bodies / query params matching each cos_task_* signature.
OUTPUT:  JSON response unwrapped from the MCP envelope ({data, meta} on 200).
DEPENDENCIES: fastapi, core.web._envelope, core.board_os.mcp_tools,
              core.thinking_os.db.
NOTES:  The board_os functions need a SQLite connection; we open one per
        request using the same DB path as the CLI.  No connection pooling
        in S4 — pooling lands with S6 if needed.
"""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Body, Depends, Query

from .._deps import make_metrics_dep, make_rate_limit_dep
from .._envelope import unwrap

_CORE_DIR = Path(__file__).resolve().parents[3]
if str(_CORE_DIR) not in sys.path:
    sys.path.insert(0, str(_CORE_DIR))

router = APIRouter(prefix="/api/board", tags=["board"])


def _db_conn() -> sqlite3.Connection:
    """Open the project SQLite DB for one request.

    PURPOSE: Provide a DB connection to board_os tools per-request.
    INPUT:   none.
    OUTPUT:  sqlite3.Connection (check_same_thread=False for async context).
    DEPENDENCIES: os.environ COS_DB_PATH, COS_PROJECT_ROOT.
    NOTES:   Caller is responsible for closing; use as a context manager or
             rely on garbage collection for short-lived request scope.
    """
    project_root = Path(os.environ.get("COS_PROJECT_ROOT") or os.getcwd()).resolve()
    db_path = os.environ.get(
        "COS_DB_PATH", str(project_root / ".coding-os" / "thinking-os.db"),
    )
    return sqlite3.connect(db_path, check_same_thread=False)


def _board_tools():
    """Lazy import for board_os mcp_tools.

    PURPOSE: Defer import so web package boots even when board_os is absent.
    INPUT:   none.
    OUTPUT:  mcp_tools module or None.
    DEPENDENCIES: core.board_os.mcp_tools.
    NOTES:   Module is cached by Python after first import.
    """
    try:
        from core.board_os import mcp_tools  # type: ignore
        return mcp_tools
    except ImportError:
        return None


def _unavailable():
    import json
    return json.dumps({
        "ok": False,
        "error": {
            "category": "unavailable",
            "retryable": False,
            "message": "board_os package not importable",
        },
    })


@router.get("/list")
async def board_list(
    swimlane: Optional[str] = Query(None),
    kind: Optional[str] = Query(None),
    epic: Optional[str] = Query(None),
    include_archive: bool = Query(False),
    limit: int = Query(50),
    _rl=Depends(make_rate_limit_dep("board.list")),
    _m=Depends(make_metrics_dep("board.list")),
):
    """Return the board state grouped by (swimlane, status).

    PURPOSE: HTTP wrapper for cos_task_board.
    INPUT:   swimlane, kind, epic, include_archive, limit (all query params).
    OUTPUT:  {data: {grouped, cards, count, wip}, meta} on 200.
    DEPENDENCIES: board_os.mcp_tools.cos_task_board.
    NOTES:   Returns all non-archive tasks by default.
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
            status_filter=None,
            include_archive=include_archive,
            limit=limit,
        )
    finally:
        conn.close()
    return unwrap(result)


@router.post("/create")
async def board_create(
    title: str = Body(...),
    swimlane: str = Body(...),
    kind: str = Body(...),
    priority: str = Body("P2"),
    appetite: str = Body("1d"),
    epic: Optional[str] = Body(None),
    labels: Optional[List[str]] = Body(None),
    outcome: Optional[str] = Body(None),
    read_first: Optional[List[str]] = Body(None),
    depends_on: Optional[List[str]] = Body(None),
    status: str = Body("icebox"),
    _rl=Depends(make_rate_limit_dep("board.create")),
    _m=Depends(make_metrics_dep("board.create")),
):
    """Create a new Scrumban task file + sync to DB.

    PURPOSE: HTTP wrapper for cos_task_create.
    INPUT:   JSON body with task fields.
    OUTPUT:  {data: {task_id, file_path, ...}, meta} on 200.
    DEPENDENCIES: board_os.mcp_tools.cos_task_create.
    NOTES:   Validates swimlane and kind against scrumban-config.yaml.
    """
    bt = _board_tools()
    if bt is None:
        return unwrap(_unavailable())
    conn = _db_conn()
    try:
        result = bt.cos_task_create(
            conn,
            title=title,
            swimlane=swimlane,
            kind=kind,
            priority=priority,
            appetite=appetite,
            epic=epic,
            labels=labels or [],
            outcome=outcome,
            read_first=read_first or [],
            depends_on=depends_on or [],
            status=status,
        )
    finally:
        conn.close()
    return unwrap(result)


@router.post("/move")
async def board_move(
    task_id: str = Body(...),
    to: str = Body(...),
    reason: Optional[str] = Body(None),
    bypass_wip: bool = Body(False),
    agent_session: Optional[str] = Body(None),
    _rl=Depends(make_rate_limit_dep("board.move")),
    _m=Depends(make_metrics_dep("board.move")),
):
    """Transition a task through the Scrumban state machine.

    PURPOSE: HTTP wrapper for cos_task_move.
    INPUT:   JSON body with task_id, to, optional reason/bypass_wip.
    OUTPUT:  {data: {task_id, previous_status, new_status, warnings}, meta} on 200.
    DEPENDENCIES: board_os.mcp_tools.cos_task_move.
    NOTES:   Enforces WIP caps unless bypass_wip=true.
    """
    bt = _board_tools()
    if bt is None:
        return unwrap(_unavailable())
    conn = _db_conn()
    try:
        result = bt.cos_task_move(
            conn,
            task_id=task_id,
            to=to,
            reason=reason,
            bypass_wip=bypass_wip,
            agent_session=agent_session,
        )
    finally:
        conn.close()
    return unwrap(result)


@router.get("/daily")
async def board_daily(
    since: str = Query("24h"),
    agent_session: Optional[str] = Query(None),
    _rl=Depends(make_rate_limit_dep("board.daily")),
    _m=Depends(make_metrics_dep("board.daily")),
):
    """Daily standup summary.

    PURPOSE: HTTP wrapper for cos_task_daily.
    INPUT:   since (e.g. "24h"), agent_session (optional).
    OUTPUT:  {data: {yesterday, in_progress, blockers, wip}, meta} on 200.
    DEPENDENCIES: board_os.mcp_tools.cos_task_daily.
    NOTES:   since supports h/d/w/m suffixes (e.g. "48h", "7d").
    """
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
async def board_retro(
    since: str = Query("7d"),
    _rl=Depends(make_rate_limit_dep("board.retro")),
    _m=Depends(make_metrics_dep("board.retro")),
):
    """Weekly retrospective metrics.

    PURPOSE: HTTP wrapper for cos_task_retro.
    INPUT:   since (e.g. "7d").
    OUTPUT:  {data: {completed, cycle_time_avg_minutes, ...}, meta} on 200.
    DEPENDENCIES: board_os.mcp_tools.cos_task_retro.
    NOTES:   Returns throughput and cycle time for the window.
    """
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
async def board_wip(
    _rl=Depends(make_rate_limit_dep("board.wip")),
    _m=Depends(make_metrics_dep("board.wip")),
):
    """WIP cap health check.

    PURPOSE: HTTP wrapper for cos_task_wip_check.
    INPUT:   none.
    OUTPUT:  {data: {counts, caps, violations, over_cap}, meta} on 200.
    DEPENDENCIES: board_os.mcp_tools.cos_task_wip_check.
    NOTES:   Returns 503 if scrumban-config.yaml is missing.
    """
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
async def board_pick(
    swimlane: Optional[str] = Query(None),
    priority_min: str = Query("P2"),
    max_candidates: int = Query(5),
    _rl=Depends(make_rate_limit_dep("board.pick")),
    _m=Depends(make_metrics_dep("board.pick")),
):
    """Top candidate tasks to start next.

    PURPOSE: HTTP wrapper for cos_task_pick.
    INPUT:   swimlane, priority_min, max_candidates.
    OUTPUT:  {data: {candidates, count}, meta} on 200.
    DEPENDENCIES: board_os.mcp_tools.cos_task_pick.
    NOTES:   Returns tasks in ready/emergency status, ranked by priority.
    """
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
