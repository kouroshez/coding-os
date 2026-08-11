"""Private sibling of board_os.mcp_tools — import via the kernel, never directly.

`cos_task_reposition` — the one tool that changes status and swimlane together,
running the state machine first and patching the frontmatter second.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from board_os.sync import sync_one
from board_os.workflow import (
    patch_task_frontmatter_scalars,
    transition,
)
from thinking_os.tools._shared import fail, ok, safe_tool

from ._mcp_shared import (
    _assign_guard,
    _current_config,
    _project_root,
    _resolve_attribution,
)

# ---------- cos_task_reposition ----------


@safe_tool
def cos_task_reposition(
    conn: sqlite3.Connection,
    *,
    task_id: str,
    swimlane: str | None = None,
    to: str | None = None,
    reason: str | None = None,
    bypass_wip: bool = False,
    force: bool = False,
    agent_session: str | None = None,
) -> str:
    """Change task status and/or swimlane (YAML frontmatter + sync).

    Status changes use the same state machine + WIP rules as ``cos_task_move``.
    Swimlane-only changes patch the task MD file then ``sync_one``.
    When both are supplied, status transition runs first, then swimlane patch.
    """
    to_eff = (to or "").strip() or None
    swim_eff = (swimlane or "").strip() or None
    if not to_eff and not swim_eff:
        return fail(
            "validation",
            "at least one of `to` (status) or `swimlane` must be provided",
        )

    row = conn.execute(
        "SELECT status, swimlane, file_path FROM tasks WHERE task_id = ?",
        (task_id,),
    ).fetchone()
    if row is None:
        return fail("not_found", f"task {task_id} not found")

    current_status = str(row[0])
    cur_sl_raw = row[1]
    cur_sl = (str(cur_sl_raw).strip() if cur_sl_raw else "") or ""
    rel_path = row[2]
    project_root = _project_root()
    file_path: Path | None = None
    if rel_path:
        candidate = project_root / rel_path
        if candidate.exists():
            file_path = candidate

    config = _current_config()
    agent_session = _resolve_attribution(agent_session)
    guard = _assign_guard(file_path, agent_session, force)
    if guard is not None:
        return fail("validation", guard)
    if swim_eff is not None:
        if config is None:
            return fail(
                "unavailable",
                "scrumban-config.yaml not found — run `cos board-config --init`",
            )
        if swim_eff not in config.swimlane_ids:
            return fail(
                "validation",
                f"swimlane {swim_eff!r} not in config; valid: {sorted(config.swimlane_ids)}",
            )

    wants_status = to_eff is not None and to_eff != current_status
    wants_swim = swim_eff is not None and swim_eff != cur_sl

    if not wants_status and not wants_swim:
        return ok(
            {
                "task_id": task_id,
                "previous_status": current_status,
                "new_status": current_status,
                "previous_swimlane": cur_sl or None,
                "new_swimlane": cur_sl or None,
                "warnings": ["no-op (already at requested status and swimlane)"],
            },
            meta={"layer": "tasks", "source": "board_os.cos_task_reposition"},
        )

    prev_status = current_status
    new_status = current_status
    warnings: list[str] = []

    if wants_status:
        result = transition(
            conn,
            task_id,
            to_eff,  # type: ignore[arg-type]
            reason=reason,
            agent_session=agent_session,
            bypass_wip=bypass_wip,
            force=force,
            config=config,
            file_path=file_path,
        )
        if not result.ok:
            return fail(
                result.error_category or "internal",
                result.error or "transition failed",
            )
        new_status = result.new_status
        warnings.extend(list(result.warnings))
        row2 = conn.execute(
            "SELECT swimlane FROM tasks WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        cur_sl = (str(row2[0]).strip() if row2 and row2[0] else "") or ""

    new_sl = cur_sl
    if wants_swim:
        if file_path is None:
            return fail(
                "unavailable",
                f"task {task_id} has no on-disk file — cannot change swimlane",
            )
        try:
            patch_task_frontmatter_scalars(file_path, {"swimlane": swim_eff})
        except (OSError, ValueError) as exc:
            return fail("validation", f"swimlane patch failed: {exc}")
        sync_one(conn, file_path, project_root=project_root)
        new_sl = swim_eff

    return ok(
        {
            "task_id": task_id,
            "previous_status": prev_status,
            "new_status": new_status,
            "previous_swimlane": cur_sl if wants_swim else None,
            "new_swimlane": new_sl if wants_swim else None,
            "warnings": warnings,
        },
        meta={"layer": "tasks", "source": "board_os.cos_task_reposition"},
    )
