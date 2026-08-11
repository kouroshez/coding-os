"""core.web.routes._board_tasks — per-task read, create, edit and transition routes."""

from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import Body, Depends, Query
from fastapi.responses import JSONResponse

from .._deps import make_metrics_dep, make_rate_limit_dep
from .._envelope import unwrap
from ._board_autospawn import _auto_spawn_safe
from ._board_shared import _board_tools, _db_conn, _unavailable, logger, router


@router.get("/task/{task_id}")
def board_task_detail(
    task_id: str,
    _rl=Depends(make_rate_limit_dep("board.task.detail")),
    _m=Depends(make_metrics_dep("board.task.detail")),
):
    """Return the full markdown content + resolved metadata for one task."""
    if not task_id or not task_id.startswith("TASK-"):
        return JSONResponse(
            status_code=400,
            content={"error": {"category": "validation", "message": "invalid task_id"}},
        )
    conn = _db_conn()
    try:
        row = conn.execute(
            "SELECT task_id, title, status, swimlane, kind, priority, "
            "appetite, epic, labels_json, file_path FROM tasks "
            "WHERE task_id = ?",
            (task_id,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return JSONResponse(
            status_code=404,
            content={"error": {"category": "not_found", "message": f"{task_id} not found"}},
        )

    import json as _json

    try:
        labels = _json.loads(row[8] or "[]")
    except (TypeError, ValueError):
        labels = []

    file_rel = row[9] or ""
    from web._project_context import current_project_root

    project_root = current_project_root()
    file_abs = (project_root / file_rel).resolve() if file_rel else None

    # Sandbox: the path must live under <project_root>/docs/tasks/.
    # Block traversal and arbitrary reads.
    tasks_dir = (project_root / "docs" / "tasks").resolve()
    exists = False
    content = ""
    size = 0
    mtime = 0
    truncated = False
    if file_abs is not None:
        try:
            file_abs.relative_to(tasks_dir)
        except ValueError:
            return JSONResponse(
                status_code=410,
                content={
                    "error": {
                        "category": "validation",
                        "message": f"task file outside docs/tasks/: {file_rel}",
                    }
                },
            )
        if file_abs.exists() and file_abs.is_file():
            exists = True
            stat = file_abs.stat()
            size = int(stat.st_size)
            mtime = int(stat.st_mtime)
            # 256 KB cap — task files rarely exceed 20 KB in practice.
            MAX_BYTES = 256 * 1024
            raw = file_abs.read_bytes()
            if len(raw) > MAX_BYTES:
                content = raw[:MAX_BYTES].decode("utf-8", errors="replace")
                content += (
                    "\n\n<!-- truncated: file is "
                    f"{len(raw):,} bytes, showing first {MAX_BYTES:,} -->\n"
                )
                truncated = True
            else:
                content = raw.decode("utf-8", errors="replace")

    return JSONResponse(
        status_code=200,
        content={
            "data": {
                "task_id": row[0],
                "file_path": file_rel,
                "exists": exists,
                "content": content,
                "size": size,
                "mtime": mtime,
                "truncated": truncated,
                "row": {
                    "title": row[1],
                    "status": row[2],
                    "swimlane": row[3],
                    "kind": row[4],
                    "priority": row[5],
                    "appetite": row[6],
                    "epic": row[7],
                    "labels": labels,
                },
            },
            "meta": {"layer": "tasks", "source": "web.board_task_detail"},
        },
    )


@router.post("/create")
def board_create(
    title: str = Body(...),
    swimlane: str = Body(...),
    kind: str = Body(...),
    priority: str = Body("P2"),
    appetite: str = Body("1d"),
    epic: str | None = Body(None),
    labels: list[str] | None = Body(None),
    outcome: str | None = Body(None),
    read_first: list[str] | None = Body(None),
    depends_on: list[str] | None = Body(None),
    status: str = Body("icebox"),
    agent_session: str | None = Body(None),
    _rl=Depends(make_rate_limit_dep("board.create")),
    _m=Depends(make_metrics_dep("board.create")),
):
    """Create a new Scrumban task file + sync to DB."""
    bt = _board_tools()
    if bt is None:
        return unwrap(_unavailable())
    # Manual panel creates are human-INITIATED. Only attribute to an agent
    # session when the caller explicitly provides one (agent-mode authoring,
    # /T12) — otherwise _resolve_attribution would tag the create to
    # whatever agent panel is active (the .active-session pointer), making a
    # human-made task look agent-led.
    if not agent_session:
        from board_os._agent_runtime import human_actor

        agent_session = human_actor()["id"]
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
            agent_session=agent_session,
        )
    finally:
        conn.close()
    return unwrap(result)


@router.post("/move")
def board_move(
    task_id: str = Body(...),
    to: str = Body(...),
    reason: str | None = Body(None),
    bypass_wip: bool = Body(False),
    force: bool = Body(False),
    agent_session: str | None = Body(None),
    _rl=Depends(make_rate_limit_dep("board.move")),
    _m=Depends(make_metrics_dep("board.move")),
):
    """Transition a task through the Scrumban state machine."""
    bt = _board_tools()
    if bt is None:
        return unwrap(_unavailable())
    # Same actor-attribution contract as board_create: an unattributed panel
    # move is the human operator — left None, _resolve_attribution would stamp
    # whatever agent session is active, recording a human drag as agent work.
    if not agent_session:
        from board_os._agent_runtime import human_actor

        agent_session = human_actor()["id"]
    conn = _db_conn()
    try:
        result = bt.cos_task_move(
            conn,
            task_id=task_id,
            to=to,
            reason=reason or "hub:board.move (no reason given)",
            bypass_wip=bypass_wip,
            force=force,
            agent_session=agent_session,
        )
    finally:
        conn.close()
    try:
        env = json.loads(result)
        if env.get("ok"):
            _auto_spawn_safe(
                task_id,
                env.get("data", {}).get("previous_status"),
                to,
                agent_session,
            )
    except Exception as exc:
        logger.debug("auto-spawn gate skipped: %s", exc)
    return unwrap(result)


@router.patch("/task/{task_id}")
def board_task_edit(
    task_id: str,
    title: str | None = Body(None),
    priority: str | None = Body(None),
    swimlane: str | None = Body(None),
    appetite: str | None = Body(None),
    epic: str | None = Body(None),
    labels: list[str] | None = Body(None),
    body: str | None = Body(None),
    _rl=Depends(make_rate_limit_dep("board.task.edit")),
    _m=Depends(make_metrics_dep("board.task.edit")),
):
    """Edit a task's frontmatter fields and/or body from the panel (human actor)."""
    bt = _board_tools()
    if bt is None:
        return unwrap(_unavailable())
    from board_os._agent_runtime import human_actor

    actor = human_actor()
    conn = _db_conn()
    try:
        result = bt.cos_task_edit(
            conn,
            task_id=task_id,
            title=title,
            priority=priority,
            swimlane=swimlane,
            appetite=appetite,
            epic=epic,
            labels=labels,
            body=body,
            actor_type="human",
            actor_id=actor["id"],
            source="web",
        )
    finally:
        conn.close()
    return unwrap(result)


@router.post("/task/{task_id}/ready")
def board_task_ready(
    task_id: str,
    ready: bool = Body(True, embed=True),
    _rl=Depends(make_rate_limit_dep("board.task.ready")),
    _m=Depends(make_metrics_dep("board.task.ready")),
):
    """Toggle the 'ready' label on a task from the panel (human actor)."""
    bt = _board_tools()
    if bt is None:
        return unwrap(_unavailable())
    from board_os._agent_runtime import human_actor

    actor = human_actor()
    conn = _db_conn()
    try:
        result = bt.cos_task_ready(conn, task_id=task_id, ready=ready, agent_session=actor["id"])
    finally:
        conn.close()
    return unwrap(result)


@router.get("/task/{task_id}/history")
def board_task_history(
    task_id: str,
    include_commits: bool = Query(True),
    _rl=Depends(make_rate_limit_dep("board.task.history")),
    _m=Depends(make_metrics_dep("board.task.history")),
):
    """Return the actor-attributed history (create + status + edits + commits) for a task."""
    bt = _board_tools()
    if bt is None:
        return unwrap(_unavailable())
    conn = _db_conn()
    try:
        result = bt.cos_task_history(conn, task_id=task_id, include_commits=include_commits)
    finally:
        conn.close()
    return unwrap(result)


@router.get("/task/{task_id}/chat-ref")
def board_task_chat_ref(
    task_id: str,
    _rl=Depends(make_rate_limit_dep("board.task.chatref")),
    _m=Depends(make_metrics_dep("board.task.chatref")),
):
    """Resolve a task's originating chat: live SDK uuid + snapshot availability."""
    if not task_id or not task_id.startswith("TASK-"):
        return JSONResponse(
            status_code=400,
            content={"error": {"category": "validation", "message": "invalid task_id"}},
        )
    conn = _db_conn()
    try:
        row = conn.execute(
            "SELECT agent_session FROM tasks WHERE task_id = ?", (task_id,)
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return JSONResponse(
            status_code=404,
            content={"error": {"category": "not_found", "message": f"{task_id} not found"}},
        )

    import glob as _glob

    from web._project_context import current_project_root

    agent_session = (row[0] or "").strip()
    sdk_uuid = None
    has_snapshot = False
    # Only resolve a real, filename-safe agent session (never 'human').
    if agent_session and agent_session != "human" and re.match(r"^[A-Za-z0-9_-]+$", agent_session):
        root = current_project_root()
        for pf in _glob.glob(str(root / ".coding-os" / "*" / "sessions" / f"{agent_session}.json")):
            try:
                rec = json.loads(Path(pf).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if rec.get("sdk_uuid"):
                sdk_uuid = rec["sdk_uuid"]
                break
        snaps = _glob.glob(
            str(root / ".coding-os" / "*" / "sessions" / "transcripts" / f"{agent_session}.jsonl")
        )
        has_snapshot = bool(snaps)

    return JSONResponse(
        status_code=200,
        content={
            "data": {
                "task_id": task_id,
                "agent_session": agent_session or None,
                "sdk_uuid": sdk_uuid,
                "has_snapshot": has_snapshot,
            },
            "meta": {"layer": "tasks", "source": "web.board_task_chat_ref"},
        },
    )


# NOTE: the per-task session-transcript preview (board_task_transcript +
# _tail_transcript) was removed — surfacing the agent's full chat transcript
# under every task was unwanted noise + a privacy leak. The snapshot file
# (cognition trace-replay) stays on disk; it is no longer exposed via the API.


@router.post("/reposition")
def board_reposition(
    task_id: str = Body(...),
    swimlane: str | None = Body(None),
    to: str | None = Body(None),
    reason: str | None = Body(None),
    bypass_wip: bool = Body(False),
    force: bool = Body(False),
    agent_session: str | None = Body(None),
    _rl=Depends(make_rate_limit_dep("board.reposition")),
    _m=Depends(make_metrics_dep("board.reposition")),
):
    """HTTP wrapper for cos_task_reposition (status and/or swimlane)."""
    bt = _board_tools()
    if bt is None:
        return unwrap(_unavailable())
    # Panel drags land here unattributed — same human-actor fallback as
    # board_create/board_move, or the drag is recorded as agent work.
    if not agent_session:
        from board_os._agent_runtime import human_actor

        agent_session = human_actor()["id"]
    conn = _db_conn()
    try:
        result = bt.cos_task_reposition(
            conn,
            task_id=task_id,
            swimlane=swimlane,
            to=to,
            reason=reason,
            bypass_wip=bypass_wip,
            force=force,
            agent_session=agent_session,
        )
    finally:
        conn.close()
    # The panel drag lands HERE (not /move) — same auto-spawn gate.
    try:
        env = json.loads(result)
        if env.get("ok") and to:
            _auto_spawn_safe(
                task_id,
                env.get("data", {}).get("previous_status"),
                to,
                agent_session,
            )
    except Exception as exc:
        logger.debug("auto-spawn gate skipped: %s", exc)
    return unwrap(result)
