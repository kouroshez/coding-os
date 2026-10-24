"""board_os workflow engine — the state machine and its atomic commit.

Public API:
    transition(conn, task_id, to_status, *, reason, agent_session,
               expected_from=None, bypass_wip=False) -> TransitionResult
    check_wip(conn, config) -> WipState
    validate_dependencies_no_cycle(conn, task_id, new_deps) -> list[str]
    patch_task_frontmatter_scalars(path, updates) -> None

This module owns `transition` itself: argument validation, the 8-state edge
check, and the BEGIN IMMEDIATE critical section that performs the move. The
concerns it composes live beside it, each changing for its own reason:

    _workflow_types        edges, WIP columns, result types (leaf)
    _workflow_wip          WIP cap counting
    _workflow_deps         dependency resolution + cycle detection
    _workflow_frontmatter  task-file reads + atomic writes
    _workflow_gates        policy gates and DoR/DoD body gates

They are re-exported below because callers and tests import them from here.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import time
from pathlib import Path

from board_os.config import STATUS_ENUM, ScrumbanConfig

from ._workflow_deps import (
    _has_task_dependencies_table,
    _validate_dependencies_no_cycle_fallback,
    dependents_of,
    incomplete_dependencies,
    validate_dependencies_no_cycle,
)
from ._workflow_frontmatter import (
    _extract_kind_from_frontmatter,
    _format_yaml_scalar_token,
    _parse_labels,
    _patch_fm_field,
    _write_status_to_frontmatter,
    patch_task_frontmatter_scalars,
)
from ._workflow_gates import (
    GateOutcome,
    evaluate_policy_gates,
    evaluate_transition_gates,
)
from ._workflow_types import (
    _VALID_TRANSITIONS,
    _WIP_COLUMN_MAP,
    TransitionError,
    TransitionResult,
    WipState,
)
from ._workflow_wip import _is_shared_pid_session, check_wip

logger = logging.getLogger("coding_os.board_os.workflow")


def transition(
    conn: sqlite3.Connection,
    task_id: str,
    to_status: str,
    *,
    reason: str | None = None,
    agent_session: str | None = None,
    expected_from: str | None = None,
    bypass_wip: bool = False,
    bypass_gates: bool = False,
    force: bool = False,
    config: ScrumbanConfig | None = None,
    file_path: Path | None = None,
) -> TransitionResult:
    if force:
        bypass_wip = True
        bypass_gates = True
    # Every history row must carry an honest reason — NULL-reason moves are
    # unauditable (the phantom in_progress→icebox reverts). Entry doors tag
    # their own source; this catches any caller that passed nothing.
    if not reason:
        reason = "(unattributed — caller passed no reason)"
    if to_status not in STATUS_ENUM:
        return TransitionResult(
            ok=False,
            task_id=task_id,
            previous_status=None,
            new_status=to_status,
            error=f"unknown status {to_status!r}; must be one of {sorted(STATUS_ENUM)}",
            error_category="validation",
        )

    row = conn.execute(
        "SELECT status, file_path, agent_session, labels_json FROM tasks WHERE task_id = ?",
        (task_id,),
    ).fetchone()
    if row is None:
        return TransitionResult(
            ok=False,
            task_id=task_id,
            previous_status=None,
            new_status=to_status,
            error=f"task {task_id} not found",
            error_category="not_found",
        )

    current_status = str(row[0])
    current_file_path = row[1]
    current_labels = _parse_labels(row[3] if len(row) > 3 else None)

    # Optimistic concurrency — R-L-29.
    if expected_from and current_status != expected_from:
        return TransitionResult(
            ok=False,
            task_id=task_id,
            previous_status=current_status,
            new_status=to_status,
            error=(
                f"status changed under us: expected {expected_from!r}, current {current_status!r}"
            ),
            error_category="transient",
        )

    if to_status == current_status:
        return TransitionResult(
            ok=True,
            task_id=task_id,
            previous_status=current_status,
            new_status=to_status,
            warnings=("no-op (already in that status)",),
        )

    valid_next = _VALID_TRANSITIONS.get(current_status, set())
    forced_warning: str | None = None
    if to_status not in valid_next:
        if not force:
            return TransitionResult(
                ok=False,
                task_id=task_id,
                previous_status=current_status,
                new_status=to_status,
                error=(
                    f"invalid transition {current_status!r} → {to_status!r}; "
                    f"valid: {sorted(valid_next) or ['(terminal)']}. "
                    "Pass force=True (or `cos task-move --force`) to override."
                ),
                error_category="validation",
            )
        forced_warning = (
            f"forced-transition {current_status!r} → {to_status!r} "
            f"(state machine disallows this; recorded in history)"
        )

    # WIP enforcement, status re-verification, and the row UPDATE all run
    # together inside the atomic BEGIN IMMEDIATE critical section below
    # — the count→write gap and the read→write gap are both inside
    # one write lock, so no concurrent transition can slip between them.
    wip_state: dict[str, int] = {}

    # ── Gates ─────────────────────────────────────────────────
    # Policy runs only when a config is supplied (the live MCP/CLI path) and
    # gates aren't explicitly bypassed — DB-only test/migration calls
    # (config=None) are unaffected.
    policy_outcome = evaluate_policy_gates(
        conn,
        task_id=task_id,
        current_status=current_status,
        to_status=to_status,
        current_labels=current_labels,
        policy=config.workflow_policy if config is not None else None,
        bypass_gates=bypass_gates,
    )
    if policy_outcome.blocked:
        return TransitionResult(
            ok=False,
            task_id=task_id,
            previous_status=current_status,
            new_status=to_status,
            error=policy_outcome.error,
            error_category=policy_outcome.error_category,
        )

    target_file_for_gate = file_path or (Path(current_file_path) if current_file_path else None)
    gate_outcome = evaluate_transition_gates(
        task_id=task_id,
        to_status=to_status,
        target_file=target_file_for_gate,
        agent_session=agent_session,
        bypass_gates=bypass_gates,
    )
    if gate_outcome.blocked:
        return TransitionResult(
            ok=False,
            task_id=task_id,
            previous_status=current_status,
            new_status=to_status,
            error=gate_outcome.error,
            error_category=gate_outcome.error_category,
            wip_state=wip_state,
        )

    # ── Atomic critical section ──────────────────────────────
    # All validation + file reads above ran lock-free. BEGIN IMMEDIATE now
    # takes the write lock up front so the status re-check, WIP count, row
    # UPDATE, MD write, and history INSERT are isolated from any concurrent
    # transition. A peer that moved the row during the lock-free gate I/O is
    # caught by the re-SELECT and the CAS rowcount.
    target_file = file_path or (Path(current_file_path) if current_file_path else None)
    warnings: list[str] = []
    if forced_warning is not None:
        warnings.append(forced_warning)
    if policy_outcome.skip_testing_warning is not None:
        warnings.append(policy_outcome.skip_testing_warning)
    warnings.extend(gate_outcome.warnings)
    now_epoch = int(time.time())

    try:
        conn.execute("BEGIN IMMEDIATE")
    except sqlite3.OperationalError as exc:
        return TransitionResult(
            ok=False,
            task_id=task_id,
            previous_status=current_status,
            new_status=to_status,
            error=f"could not acquire board write lock (busy): {exc}",
            error_category="transient",
        )

    md_backup: str | None = None
    try:
        # Re-verify status under the lock — gate validation did file I/O,
        # widening the read→write window; a peer may have moved it since.
        locked_row = conn.execute(
            "SELECT status FROM tasks WHERE task_id = ?", (task_id,)
        ).fetchone()
        locked_status = str(locked_row[0]) if locked_row else None
        if locked_status != current_status:
            conn.rollback()
            return TransitionResult(
                ok=False,
                task_id=task_id,
                previous_status=locked_status,
                new_status=to_status,
                error=(
                    f"status changed under us: expected {current_status!r}, "
                    f"current {locked_status!r} — re-read and retry"
                ),
                error_category="transient",
            )

        # WIP cap, now race-free (count + UPDATE share the write lock).
        if config is not None and not bypass_wip:
            target_col = _WIP_COLUMN_MAP.get(to_status)
            if target_col:
                state = check_wip(conn, config, agent_session=agent_session)
                wip_state = dict(state.counts)
                cap = state.caps.get(target_col)
                if (
                    cap is not None
                    and state.counts.get(target_col, 0) >= cap
                    and os.environ.get("COS_WIP_OVERRIDE") != "1"
                ):
                    conn.rollback()
                    return TransitionResult(
                        ok=False,
                        task_id=task_id,
                        previous_status=current_status,
                        new_status=to_status,
                        error=(
                            f"WIP cap reached for {target_col}: "
                            f"{state.counts.get(target_col)}/{cap}. "
                            f"Complete another task first or set "
                            f"COS_WIP_OVERRIDE=1 to force."
                        ),
                        error_category="validation",
                        wip_state=wip_state,
                    )

        # CAS UPDATE — the AND status=? guard is the last-line defense: a
        # rowcount other than 1 means the expected pre-state vanished.
        cur = conn.execute(
            "UPDATE tasks SET status = ?, agent_session = ?, "
            "started_at = CASE WHEN ? = 'in_progress' AND started_at IS NULL "
            "                  THEN ? ELSE started_at END, "
            "completed_at = CASE WHEN ? = 'complete' THEN ? "
            "                    WHEN ? IN ('ready','in_progress','testing','emergency') "
            "                    THEN NULL ELSE completed_at END "
            "WHERE task_id = ? AND status = ?",
            (
                to_status,
                agent_session,
                to_status,
                now_epoch,
                to_status,
                now_epoch,
                to_status,
                task_id,
                current_status,
            ),
        )
        if cur.rowcount != 1:
            conn.rollback()
            return TransitionResult(
                ok=False,
                task_id=task_id,
                previous_status=current_status,
                new_status=to_status,
                error="status changed under us (CAS miss) — re-read and retry",
                error_category="transient",
            )

        # MD frontmatter write — inside the txn. The writer itself is atomic
        # (tmp + os.replace), so its OWN failure leaves the original intact.
        # We additionally snapshot the file first: if a LATER step (history
        # INSERT / commit) raises, the outer except restores it — so a
        # rolled-back transition changes neither the DB nor the file, instead
        # of leaving the file's status ahead of the DB it just reverted.
        if target_file is not None:
            try:
                md_backup = target_file.read_text(encoding="utf-8")
            except OSError:
                md_backup = None
            try:
                _write_status_to_frontmatter(target_file, to_status, agent_session=agent_session)
            except FileNotFoundError:
                warnings.append(f"MD file missing: {target_file} — DB-only transition")
            except Exception as exc:  # pragma: no cover
                conn.rollback()
                return TransitionResult(
                    ok=False,
                    task_id=task_id,
                    previous_status=current_status,
                    new_status=to_status,
                    error=f"MD write failed: {exc}",
                    error_category="unavailable",
                )
        else:
            warnings.append("no file_path — DB-only transition")

        # task_status_history gained override_reason/override_actor in
        # migration v20. Detect column presence so this code
        # works on a DB before v20 has run yet (test fixtures, fresh init).
        has_override_cols = bool(
            conn.execute(
                "SELECT 1 FROM pragma_table_info('task_status_history') "
                "WHERE name = 'override_reason' LIMIT 1"
            ).fetchone()
        )
        if has_override_cols:
            conn.execute(
                "INSERT INTO task_status_history "
                "(task_id, old_status, new_status, agent_session, reason, "
                " transitioned_at, override_reason, override_actor) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    task_id,
                    current_status,
                    to_status,
                    agent_session,
                    reason,
                    now_epoch,
                    gate_outcome.override_reason,
                    gate_outcome.override_actor,
                ),
            )
        else:
            conn.execute(
                "INSERT INTO task_status_history "
                "(task_id, old_status, new_status, agent_session, reason, transitioned_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (task_id, current_status, to_status, agent_session, reason, now_epoch),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        # Undo a successful MD write whose transaction then failed, so the
        # file never reports a status the DB rolled back (Finding A).
        if md_backup is not None and target_file is not None:
            try:
                target_file.write_text(md_backup, encoding="utf-8")
            except OSError as restore_exc:
                logger.debug("MD restore after rollback failed: %s", restore_exc)
        raise

    return TransitionResult(
        ok=True,
        task_id=task_id,
        previous_status=current_status,
        new_status=to_status,
        warnings=tuple(warnings),
        wip_state=wip_state,
    )


__all__ = [
    "_VALID_TRANSITIONS",
    "_WIP_COLUMN_MAP",
    "GateOutcome",
    "TransitionError",
    "TransitionResult",
    "WipState",
    "_extract_kind_from_frontmatter",
    "_format_yaml_scalar_token",
    "_has_task_dependencies_table",
    "_is_shared_pid_session",
    "_parse_labels",
    "_patch_fm_field",
    "_validate_dependencies_no_cycle_fallback",
    "_write_status_to_frontmatter",
    "check_wip",
    "dependents_of",
    "evaluate_policy_gates",
    "evaluate_transition_gates",
    "incomplete_dependencies",
    "patch_task_frontmatter_scalars",
    "transition",
    "validate_dependencies_no_cycle",
]
