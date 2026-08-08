"""Private sibling of board_os.mcp_tools — import via the kernel, never directly."""

from __future__ import annotations

import json
import os
import re
import sqlite3
from pathlib import Path

from board_os.config import (
    READY_LABEL,
)
from board_os.sync import sync_one
from board_os.workflow import (
    dependents_of,
    incomplete_dependencies,
    patch_task_frontmatter_scalars,
    transition,
)
from thinking_os.tools._shared import fail, ok, safe_tool

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
            # silent skip would close an unverifiable task (TASK-532).
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


# ---------- cos_task_ready ----------


def _labels_list_from_json(raw: object) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, (list, tuple)):
        return [str(x) for x in raw]
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return [t.strip() for t in raw.split(",") if t.strip()]
        if isinstance(parsed, list):
            return [str(x) for x in parsed]
    return []


def _patch_labels_line(file_path: Path, labels: list[str]) -> None:
    content = file_path.read_text(encoding="utf-8")
    flow = "[" + ", ".join(labels) + "]"
    fm_re = re.compile(r"^(---\s*\n.*?\n---\s*\n)", re.DOTALL)
    m = fm_re.match(content)
    if not m:
        raise ValueError(f"{file_path}: no frontmatter to patch")
    head = m.group(1)
    label_re = re.compile(r"^labels:.*$", re.MULTILINE)
    if label_re.search(head):
        new_head = label_re.sub(f"labels: {flow}", head, count=1)
    else:
        new_head = head.replace("---\n", f"---\nlabels: {flow}\n", 1)
    new_content = new_head + content[m.end() :]
    tmp = file_path.with_suffix(file_path.suffix + ".tmp")
    tmp.write_text(new_content, encoding="utf-8")
    os.replace(tmp, file_path)


def _ready_dor_check(
    file_path: Path,
    agent_session: str | None,
) -> tuple[list[dict[str, str]], str | None]:
    from board_os.transition_gates import GatesConfigError, load_gates_config
    from board_os.transition_gates_validator import evaluate_dor, evaluate_override
    from board_os.workflow import _extract_kind_from_frontmatter

    try:
        body = file_path.read_text(encoding="utf-8")
        kind = _extract_kind_from_frontmatter(body) or "feature"
        config = load_gates_config()
        result = evaluate_dor(kind, body, config)
    except (GatesConfigError, OSError, ValueError) as exc:
        return [{"code": "DOR_CHECK_SKIPPED", "severity": "warn", "message": str(exc)}], None

    gaps = [
        {"code": m.code, "severity": m.severity.value, "message": m.message}
        for m in result.messages
    ]
    # Warn-default: surface gaps but still let the label land. Block only when
    # the operator opted into COS_READY_DOR=strict AND the DoR actually fails.
    if not result.blocked or os.environ.get("COS_READY_DOR") != "strict":
        return gaps, None

    if os.environ.get("COS_DOR_OVERRIDE") == "1":
        override_result, _request = evaluate_override(
            "dor",
            reason=os.environ.get("COS_OVERRIDE_REASON"),
            actor=os.environ.get("COS_AGENT") or agent_session,
            config=config,
        )
        if not override_result.blocked:
            return gaps, None  # override accepted — proceed, gaps stay advisory
        rejected = "; ".join(m.message for m in override_result.messages)
        summary = "; ".join(f"[{g['code']}] {g['message']}" for g in gaps)
        return gaps, f"DoR not met and override rejected: {summary} | {rejected}"

    summary = "; ".join(f"[{g['code']}] {g['message']}" for g in gaps)
    return gaps, (
        f"ready refused — Definition of Ready not met: {summary}. "
        "Fix the task body, unset COS_READY_DOR, or set "
        "COS_DOR_OVERRIDE=1 with a COS_OVERRIDE_REASON."
    )


@safe_tool
def cos_task_ready(
    conn: sqlite3.Connection,
    *,
    task_id: str,
    ready: bool = True,
    agent_session: str | None = None,
) -> str:
    """Add or remove the 'ready' label that gates icebox→in_progress."""
    row = conn.execute(
        "SELECT status, file_path, labels_json FROM tasks WHERE task_id = ?",
        (task_id,),
    ).fetchone()
    if row is None:
        return fail("not_found", f"task {task_id} not found")

    labels = _labels_list_from_json(row[2])
    has_ready = READY_LABEL in labels
    if ready == has_ready:
        return ok(
            {
                "task_id": task_id,
                "ready": ready,
                "labels": labels,
                "warnings": [
                    f"no-op (label '{READY_LABEL}' already {'set' if ready else 'absent'})"
                ],
            },
            meta={"layer": "tasks", "source": "board_os.cos_task_ready"},
        )

    project_root = _project_root()
    rel_path = row[1]
    file_path = project_root / rel_path if rel_path else None

    # DoR surfacing (TASK-258): reuse the icebox→in_progress validator so a
    # task can't be silently labeled ready while incomplete. Runs BEFORE the
    # label mutation so a strict-mode refusal leaves no half-applied change.
    dor_gaps: list[dict[str, str]] = []
    if ready and file_path is not None and file_path.exists():
        dor_gaps, block_reason = _ready_dor_check(file_path, agent_session)
        if block_reason is not None:
            return fail("validation", block_reason)

    if ready:
        labels.append(READY_LABEL)
    else:
        labels = [lbl for lbl in labels if lbl != READY_LABEL]

    if file_path is not None and file_path.exists():
        try:
            _patch_labels_line(file_path, labels)
        except (OSError, ValueError) as exc:
            return fail("validation", f"labels patch failed: {exc}")
        sync_one(conn, file_path, project_root=project_root)
    else:
        conn.execute(
            "UPDATE tasks SET labels_json = ? WHERE task_id = ?",
            (json.dumps(labels), task_id),
        )
        conn.commit()

    data: dict[str, object] = {
        "task_id": task_id,
        "ready": ready,
        "labels": labels,
        "status": str(row[0]),
    }
    if dor_gaps:
        data["dor"] = dor_gaps
    return ok(data, meta={"layer": "tasks", "source": "board_os.cos_task_ready"})


# ---------- cos_task_reclaim (zombie in_progress recovery) ----------
