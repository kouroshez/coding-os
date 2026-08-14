"""Private sibling of board_os.mcp_tools — import via the kernel, never directly.

`cos_task_move` and everything a completion pulls behind it: the outcome
record, the learning-loop closure, and the dependent cascade. The cascade calls
back into `cos_task_move`, so the two stay in one module; the ready label and
the reposition tool live in leaves and are re-exported here.
"""

from __future__ import annotations

import json
import os
import sqlite3

from board_os.config import (
    READY_LABEL,
)
from board_os.workflow import (
    dependents_of,
    incomplete_dependencies,
    transition,
)
from thinking_os.tools._shared import fail, ok, safe_tool

from ._mcp_ready import (
    _labels_list_from_json as _labels_list_from_json,
    _patch_labels_line as _patch_labels_line,
    _ready_dor_check as _ready_dor_check,
    cos_task_ready as cos_task_ready,
)
from ._mcp_reposition import cos_task_reposition as cos_task_reposition
from ._mcp_shared import (  # noqa: F401
    _BOARD_SELECT,
    _COMMIT_SCAN_CAP,
    _COMPLETION_EVIDENCE_RE,
    _SLUG_RE,
    _STRANDED_SCAN_LIMIT,
    _TASK_ID_ALLOCATORS,
    _actor_view,
    _agent_label,
    _allocate_with_prefix,
    _assign_guard,
    _commits_referencing,
    _completion_evidence,
    _current_config,
    _derive_ns_from_git,
    _detect_forge,
    _flag_stale,
    _has_table,
    _humanize_duration,
    _last_log_line,
    _LocalAllocator,
    _namespace_segment,
    _NamespacedAllocator,
    _next_task_id,
    _normalize_external_ref,
    _parse_since,
    _project_root,
    _resolve_attribution,
    _resolve_task_id_allocator,
    _sla_threshold_seconds,
    _slugify,
    _status_dwell_seconds,
    _task_card,
    check_cycle,
    cos_task_link,
    logger,
)


def _record_completion_outcome_safe(conn: sqlite3.Connection, task_id: str) -> None:
    # Fire-and-forget: feed an MCP-driven completion into the learning loop,
    # mirroring the CLI task-done path. Without this, tasks closed via
    # cos_task_move never produced a task_outcome row.
    try:
        from thinking_os.record_outcome import record_outcome

        krow = conn.execute("SELECT kind FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        kind = (krow[0] if krow else "") or "feature"
        ttype = {
            "bug": "fix",
            "feature": "feat",
            "refactor": "refactor",
            "docs": "docs",
            "test": "test",
            "chore": "infra",
            "spike": "spike",
            "security": "security",
        }.get(kind, "feat")
        db_path = os.environ.get(
            "COS_DB_PATH", str(_project_root() / ".coding-os" / "coding-os.db")
        )
        record_outcome(task_id=task_id, task_type=ttype, outcome="success", db_path=db_path)
    except Exception as exc:
        logger.debug("MCP completion outcome failed for %s: %s", task_id, exc)


def _close_learning_loop_safe(conn: sqlite3.Connection) -> None:
    # Fire-and-forget: validate the lessons surfaced this task, mirroring the
    # task-done Bash hook (remind-learn-validate.sh) which NEVER fires on an MCP
    # tool call — the gap that left pattern_validations empty and every pattern
    # stuck below the Trusted tier. The Bash hook owns closure whenever a shell
    # ran `cos task-move` (COS_PANEL_DIR is set there); a direct MCP call runs in
    # the long-lived server (no COS_PANEL_DIR, no Bash hook), so ONLY there does
    # this path close the loop — no double-validation.
    if os.environ.get("COS_PANEL_DIR"):
        return
    try:
        from thinking_os.gate_marker import newest_panel_gate
        from thinking_os.tools.learning import validate_surfaced_lessons

        gate = newest_panel_gate()
        if gate is None:
            return
        panel_dir = gate.parent
        suggestions = panel_dir / ".learn-suggestions"
        if not suggestions.exists() or suggestions.stat().st_size == 0:
            return
        sid_file = panel_dir / "session-id"
        session_id = sid_file.read_text(encoding="utf-8").strip() if sid_file.exists() else ""
        if not session_id:
            return
        validate_surfaced_lessons(conn, session_id=session_id, suggestions_path=str(suggestions))
        suggestions.write_text("", encoding="utf-8")  # per-task boundary, like the hook
    except Exception as exc:
        logger.debug("MCP learning-loop closure failed: %s", exc)


_TERMINAL_DEP_STATES = ("archive",)


def cascade_ready_dependents(
    conn: sqlite3.Connection,
    completed_task_id: str,
    *,
    agent_session: str | None = None,
) -> dict[str, list]:
    """Auto-ready every dependent of `completed_task_id` now unblocked + DoR-complete.

    Run after a task transitions to `complete`. Each dependent is classified:
    `readied` (all deps complete AND body DoR met — the ready label is added,
    moving blocked→icebox first), `needs_authoring` (all deps complete but the
    body DoR is incomplete — surfaced, not silently hidden), or `still_blocked`
    (another dep is open, or a dep is archived/cancelled — left blocked with a
    reason instead of hanging). Already-ready or active dependents are skipped.
    """
    report: dict[str, list] = {"readied": [], "needs_authoring": [], "still_blocked": []}
    project_root = _project_root()
    for dependent_id in dependents_of(conn, completed_task_id):
        row = conn.execute(
            "SELECT status, file_path, labels_json FROM tasks WHERE task_id = ?",
            (dependent_id,),
        ).fetchone()
        if row is None:
            continue
        status = str(row[0])
        # Only backlog cards are cascade targets; an active/done card is the
        # owning session's concern, never auto-mutated here.
        if status not in ("icebox", "blocked"):
            continue
        if READY_LABEL in _labels_list_from_json(row[2]):
            continue

        pending = incomplete_dependencies(conn, dependent_id)
        if pending:
            terminal = [
                dep
                for dep in pending
                if (
                    conn.execute("SELECT status FROM tasks WHERE task_id = ?", (dep,)).fetchone()
                    or (None,)
                )[0]
                in _TERMINAL_DEP_STATES
            ]
            reason = (
                f"dependency terminal-failed (archived): {', '.join(terminal)}"
                if terminal
                else f"still waiting on: {', '.join(pending)}"
            )
            report["still_blocked"].append({"task_id": dependent_id, "reason": reason})
            continue

        # All deps complete. Gate on the body DoR before auto-readying so the
        # cascade never marks an unauthored stub pullable.
        file_path = project_root / row[1] if row[1] else None
        dor_gaps: list[dict[str, str]] = []
        if file_path is not None and file_path.exists():
            dor_gaps, _ = _ready_dor_check(file_path, agent_session)
        if dor_gaps:
            report["needs_authoring"].append({"task_id": dependent_id, "dor": dor_gaps})
            continue

        # blocked must return to icebox before it can carry the ready label and
        # be pulled (blocked→in_progress skips the icebox ready gate otherwise).
        if status == "blocked":
            move_env = json.loads(
                cos_task_move(conn, task_id=dependent_id, to="icebox", agent_session=agent_session)
            )
            if not move_env.get("ok"):
                report["still_blocked"].append(
                    {"task_id": dependent_id, "reason": "could not unblock to icebox"}
                )
                continue
        ready_env = json.loads(
            cos_task_ready(conn, task_id=dependent_id, agent_session=agent_session)
        )
        if ready_env.get("ok"):
            report["readied"].append(dependent_id)
        else:
            report["still_blocked"].append(
                {"task_id": dependent_id, "reason": "ready label add failed"}
            )
    return report


def _cascade_ready_dependents_safe(
    conn: sqlite3.Connection, task_id: str, agent_session: str | None
) -> dict[str, list]:
    # Fire-and-forget: the completion itself already committed; a cascade
    # failure must never turn a successful close into an error.
    try:
        return cascade_ready_dependents(conn, task_id, agent_session=agent_session)
    except Exception as exc:
        logger.debug("dependent cascade after %s complete failed: %s", task_id, exc)
        return {"readied": [], "needs_authoring": [], "still_blocked": []}


@safe_tool
def _auto_reclaim_zombies_safe(conn: sqlite3.Connection) -> None:
    """Best-effort zombie reclaim run before an in_progress pull. Frees idle
    in_progress tasks of inactive sessions so the board self-heals without a
    manual `cos task-reclaim`. Never raises (cos_task_reclaim is @safe_tool)."""
    try:
        from ._mcp_reclaim import cos_task_reclaim

        cos_task_reclaim(conn)
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("auto-reclaim before start skipped: %s", exc)


@safe_tool
def cos_task_move(
    conn: sqlite3.Connection,
    *,
    task_id: str,
    to: str,
    reason: str | None = None,
    bypass_wip: bool = False,
    bypass_gates: bool = False,
    force: bool = False,
    agent_session: str | None = None,
) -> str:
    config = _current_config()

    row = conn.execute(
        "SELECT file_path FROM tasks WHERE task_id = ?",
        (task_id,),
    ).fetchone()
    file_path = None
    if row and row[0]:
        candidate = _project_root() / row[0]
        if candidate.exists():
            file_path = candidate
        elif to == "complete" and not bypass_gates and not force:
            # Fail CLOSED when the file is gone: the DoD gate can't run, and a
            # silent skip would close an unverifiable task.
            return fail(
                "validation",
                f"task file not found — cannot verify DoD: {row[0]}. Re-materialize "
                "the task file before closing (it desynced from the DB).",
            )

    agent_session = _resolve_attribution(agent_session)
    guard = _assign_guard(file_path, agent_session, force)
    if guard is not None:
        return fail("validation", guard)

    # Free zombie in_progress of dead/idle sessions before a pull, so a live
    # agent isn't blocked by a crashed peer and the board self-heals without a
    # manual `cos task-reclaim`. Conservative — only idle + owner-inactive
    # tasks qualify (see cos_task_reclaim). Best-effort; never blocks the move.
    if to == "in_progress" and not bypass_wip and not force:
        _auto_reclaim_zombies_safe(conn)

    result = transition(
        conn,
        task_id,
        to,
        reason=reason,
        agent_session=agent_session,
        bypass_wip=bypass_wip,
        bypass_gates=bypass_gates,
        force=force,
        config=config,
        file_path=file_path,
    )
    if not result.ok:
        return fail(result.error_category or "internal", result.error or "transition failed")

    data: dict = {
        "task_id": result.task_id,
        "previous_status": result.previous_status,
        "new_status": result.new_status,
        "warnings": list(result.warnings),
        "wip": result.wip_state,
    }
    if result.new_status == "complete":
        _record_completion_outcome_safe(conn, task_id)
        _close_learning_loop_safe(conn)
        cascade = _cascade_ready_dependents_safe(conn, task_id, agent_session)
        if any(cascade.values()):
            data["cascade"] = cascade

    return ok(data, meta={"layer": "tasks", "source": "board_os.cos_task_move"})
