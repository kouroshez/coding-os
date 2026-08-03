"""board_os workflow engine — state machine + WIP enforcement.

One module, one SSOT for:
- Valid status transitions (8-state machine, plan §6.4)
- WIP cap enforcement (plan §3 P-L-3, config-driven)
- Atomic frontmatter writes (temp file + rename)
- task_status_history auditing
- Optimistic concurrency (plan §17, R-L-29 DFS cycle check)

Public API:
    transition(conn, task_id, to_status, *, reason, agent_session,
               expected_from=None, bypass_wip=False) -> TransitionResult
    check_wip(conn, config) -> WipState
    validate_dependencies_no_cycle(conn, task_id, new_deps) -> list[str]
    patch_task_frontmatter_scalars(path, updates) -> None
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from board_os.config import READY_LABEL, STATUS_ENUM, ScrumbanConfig

logger = logging.getLogger("coding_os.board_os.workflow")


# Valid transition edges: {from_status: {to_statuses}}
# "ready" was a dedicated column in earlier versions — it has been folded
# into an `icebox + "ready" label` combination so the board has one less
# queue and "ready" becomes something the agent tags rather than a
# destination to drag tasks into.  Any legacy task still carrying
# status='ready' is migrated to 'icebox' via _migrate_v19_drop_ready_status.
# archive is *soft-terminal*: the only way out is back to icebox or complete,
# which is how a user recovers from an accidental archive.  Any other target
# requires an explicit --force flag (workflow.transition(..., force=True)) so
# mis-clicks still surface an error, but a human can always self-correct.
_VALID_TRANSITIONS: dict[str, set[str]] = {
    "icebox": {"in_progress", "emergency", "archive"},
    "emergency": {"in_progress", "icebox"},
    "in_progress": {"testing", "blocked", "icebox", "emergency", "complete"},
    "testing": {"complete", "in_progress", "blocked"},
    "complete": {"archive"},
    "blocked": {"in_progress", "emergency", "icebox"},
    "archive": {"icebox", "complete"},  # un-archive paths (see note above)
}

# Statuses that count toward the WIP cap for a given column.
_WIP_COLUMN_MAP: dict[str, str] = {
    "in_progress": "in_progress",
    "testing": "testing",
    "emergency": "emergency",
}


@dataclass(frozen=True)
class TransitionResult:
    ok: bool
    task_id: str
    previous_status: str | None
    new_status: str
    warnings: tuple[str, ...] = field(default_factory=tuple)
    wip_state: dict[str, int] = field(default_factory=dict)
    error: str | None = None
    error_category: str | None = None


@dataclass(frozen=True)
class WipState:
    """Current WIP counts vs. configured caps per column."""

    counts: dict[str, int]
    caps: dict[str, int]
    violations: tuple[str, ...]

    def violates(self, column: str) -> bool:
        cap = self.caps.get(column)
        return cap is not None and self.counts.get(column, 0) >= cap


class TransitionError(ValueError):
    """Raised on invalid transitions. Carries suggested paths."""

    def __init__(
        self,
        message: str,
        *,
        task_id: str,
        from_status: str,
        to_status: str,
        suggested: list[str] | None = None,
    ) -> None:
        self.task_id = task_id
        self.from_status = from_status
        self.to_status = to_status
        self.suggested = suggested or []
        super().__init__(message)


# ---------- Public API ----------


def _is_shared_pid_session(session: str | None) -> bool:
    # resolve_agent_session's last-resort synthetic is ses-<agent>-pid<PID>.
    # For the long-lived MCP server that PID is shared by ALL panels, so a
    # per-session cap keyed on it is NOT panel-isolated.
    if not session or not session.startswith("ses-"):
        return False
    idx = session.rfind("-pid")
    return idx != -1 and session[idx + len("-pid") :].isdigit()


def check_wip(
    conn: sqlite3.Connection,
    config: ScrumbanConfig,
    *,
    agent_session: str | None = None,
) -> WipState:
    # in_progress is a per-worker focus cap: when per_session_wip is on
    # and a session is known, count only that session's in_progress
    # tasks so concurrent sessions don't block each other on a global
    # cap. testing / emergency stay board-global (queue / SEV limits).
    per_session = bool(config.workflow_policy.per_session_wip and agent_session)
    if per_session and _is_shared_pid_session(agent_session):
        # Attribution fell back to the shared MCP-server PID synthetic — surface
        # it rather than silently applying an in_progress cap that is shared
        # across sibling panels instead of being per-panel.
        logger.warning(
            "per-session WIP cap degraded: agent_session %r is a shared "
            "ses-<agent>-pid<PID> synthetic (panel attribution unresolved); "
            "the in_progress cap is shared across sibling panels, not per-panel.",
            agent_session,
        )
    counts: dict[str, int] = {}
    for status in _WIP_COLUMN_MAP.values():
        if per_session and status == "in_progress":
            row = conn.execute(
                "SELECT COUNT(*) FROM tasks WHERE status = ? AND agent_session = ?",
                (status, agent_session),
            ).fetchone()
        else:
            row = conn.execute("SELECT COUNT(*) FROM tasks WHERE status = ?", (status,)).fetchone()
        counts[status] = int(row[0]) if row else 0
    caps = {
        "in_progress": config.wip_limits.in_progress,
        "testing": config.wip_limits.testing,
        "emergency": config.wip_limits.emergency,
    }
    violations = tuple(col for col in caps if counts.get(col, 0) > caps[col])
    return WipState(counts=counts, caps=caps, violations=violations)


def _has_task_dependencies_table(conn: sqlite3.Connection) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='task_dependencies'"
        ).fetchone()
        is not None
    )


def incomplete_dependencies(conn: sqlite3.Connection, task_id: str) -> list[str]:
    """Return the depends_on ids of `task_id` whose status is not 'complete'.

    Reuses the same junction-then-JSON-column resolution as
    tools.tasks.task_dependencies: on a v35+ DB it joins the indexed
    task_dependencies junction; otherwise it reads the JSON `dependencies`
    column. A dep id that has no matching tasks row (never synced) counts as
    incomplete so a dangling prerequisite can't silently unblock a pull.
    """
    if _has_task_dependencies_table(conn):
        try:
            rows = conn.execute(
                "SELECT d.depends_on, t.status "
                "FROM task_dependencies d "
                "LEFT JOIN tasks t ON t.task_id = d.depends_on "
                "WHERE d.task_id = ? ORDER BY d.depends_on ASC",
                (task_id,),
            ).fetchall()
            return [str(dep) for dep, status in rows if status != "complete"]
        except sqlite3.OperationalError as exc:
            logger.debug("incomplete_dependencies junction failed, JSON fallback: %s", exc)

    row = conn.execute("SELECT dependencies FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
    if row is None or not row[0]:
        return []
    try:
        dep_ids = [str(d) for d in json.loads(row[0])]
    except (json.JSONDecodeError, TypeError):
        return []
    if not dep_ids:
        return []
    placeholders = ",".join("?" * len(dep_ids))
    status_by_dep = {
        str(r[0]): str(r[1])
        for r in conn.execute(
            f"SELECT task_id, status FROM tasks WHERE task_id IN ({placeholders})",
            dep_ids,
        ).fetchall()
    }
    return [dep for dep in dep_ids if status_by_dep.get(dep) != "complete"]


def dependents_of(conn: sqlite3.Connection, task_id: str) -> list[str]:
    """Return the ids of tasks that declare `task_id` in their depends_on.

    The reverse of incomplete_dependencies. Drives the completion cascade:
    when a prerequisite completes, its dependents are the only candidates that
    could newly become runnable. Uses the indexed task_dependencies(depends_on)
    junction on a v35+ DB; otherwise scans the JSON `dependencies` column.
    """
    if _has_task_dependencies_table(conn):
        try:
            rows = conn.execute(
                "SELECT task_id FROM task_dependencies WHERE depends_on = ? ORDER BY task_id ASC",
                (task_id,),
            ).fetchall()
            return [str(r[0]) for r in rows]
        except sqlite3.OperationalError as exc:
            logger.debug("dependents_of junction failed, JSON fallback: %s", exc)

    rows = conn.execute(
        "SELECT task_id, dependencies FROM tasks "
        "WHERE dependencies IS NOT NULL AND dependencies != ''"
    ).fetchall()
    found: list[str] = []
    for dependent_id, deps_raw in rows:
        try:
            deps = [str(d) for d in json.loads(deps_raw)]
        except (json.JSONDecodeError, TypeError):
            continue
        if task_id in deps:
            found.append(str(dependent_id))
    return sorted(found)


def validate_dependencies_no_cycle(
    conn: sqlite3.Connection, task_id: str, new_deps: list[str]
) -> list[str]:
    """Detect cycles a proposed task_id -> new_deps edge set would create. R-L-29.

    On a v35 DB this runs a targeted recursive CTE over the task_dependencies
    junction — for each proposed dep it asks whether that dep can already reach
    task_id, traversing only the reachable subgraph instead of loading every
    task row (TASK-229). Falls back to the full-scan DFS on a pre-v35 DB.
    Returns a list of cycle paths (empty if no cycle).
    """
    if not new_deps:
        return []
    if not _has_task_dependencies_table(conn):
        return _validate_dependencies_no_cycle_fallback(conn, task_id, new_deps)

    cycles: list[str] = []
    if task_id in new_deps:
        cycles.append(f"{task_id} → {task_id}")  # trivial self-cycle
    for dep in new_deps:
        if dep == task_id:
            continue
        # Can `dep` already reach task_id (excluding task_id's own edges, which
        # this edit replaces)? If so, task_id -> dep closes a cycle. depth guard
        # terminates on any pre-existing cycle in the data.
        # UNION (not UNION ALL) dedups on tid, so a dense DAG with many distinct
        # paths to the same node is bounded to O(reachable nodes) instead of
        # enumerating every path — and the dedup makes any pre-existing data
        # cycle terminate without needing a depth guard.
        row = conn.execute(
            """
            WITH RECURSIVE reachable(tid) AS (
                SELECT ?
                UNION
                SELECT td.depends_on
                FROM task_dependencies td
                JOIN reachable r ON td.task_id = r.tid
                WHERE td.task_id != ?
            )
            SELECT 1 FROM reachable WHERE tid = ? LIMIT 1
            """,
            (dep, task_id, task_id),
        ).fetchone()
        if row:
            cycles.append(f"{task_id} → {dep} → … → {task_id}")
    return cycles


def _validate_dependencies_no_cycle_fallback(
    conn: sqlite3.Connection, task_id: str, new_deps: list[str]
) -> list[str]:
    """Pre-v35 fallback: DFS over the full dependency graph (loads all rows)."""
    deps_by_task: dict[str, list[str]] = {}
    for row in conn.execute("SELECT task_id, dependencies FROM tasks"):
        if row[0] == task_id:
            continue
        raw = row[1] or ""
        # Dependencies may be stored as JSON (new style) or as a
        # newline/comma-separated string (legacy). Handle both.
        parsed_deps: list[str] = []
        if isinstance(raw, str) and raw.strip():
            text = raw.strip()
            if text.startswith("["):
                try:
                    parsed_deps = [str(d) for d in json.loads(text)]
                except json.JSONDecodeError:
                    parsed_deps = []
            else:
                import re as _re

                parsed_deps = _re.findall(r"TASK-(?:[A-Z][A-Z0-9]*-)?\d+", text)
        deps_by_task[row[0]] = parsed_deps
    deps_by_task[task_id] = list(new_deps)

    cycles: list[str] = []
    visited: set[str] = set()
    stack: list[str] = []

    def dfs(node: str) -> None:
        if node in stack:
            cycle = stack[stack.index(node) :] + [node]
            cycles.append(" → ".join(cycle))
            return
        if node in visited:
            return
        visited.add(node)
        stack.append(node)
        for dep in deps_by_task.get(node, []):
            dfs(dep)
        stack.pop()

    dfs(task_id)
    return cycles


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

    # ── Workflow-policy gates (config-driven, state machine) ──
    # Both default-on; a consumer relaxes them via scrumban-config.yaml
    # `workflow_policy:`. Policy runs only when a config is supplied
    # (the live MCP/CLI path) and gates aren't explicitly bypassed —
    # DB-only test/migration calls (config=None) are unaffected.
    policy = config.workflow_policy if config is not None else None

    # Ready hard-gate: a task must be deliberately marked `ready` before
    # it can be pulled from the backlog. icebox→in_progress is the only
    # pull edge; emergency→in_progress (the fast lane) stays exempt.
    if (
        policy is not None
        and policy.require_ready_label
        and not bypass_gates
        and current_status == "icebox"
        and to_status == "in_progress"
        and READY_LABEL not in current_labels
    ):
        return TransitionResult(
            ok=False,
            task_id=task_id,
            previous_status=current_status,
            new_status=to_status,
            error=(
                f"task not ready: add the '{READY_LABEL}' label before pulling "
                f"it into in_progress — `cos task-ready {task_id}` "
                f"(or escalate via emergency). Override: force=True."
            ),
            error_category="validation",
        )

    # Dependency gate: a task whose prerequisites are not yet complete cannot
    # be pulled. Same pull edge as the ready gate (icebox→in_progress);
    # emergency→in_progress (the fast lane) stays exempt so a fire never waits
    # on backlog. Category `transient` — the codebase's retryable-by-default
    # category (the canonical retryable "conflict" in the MCP envelope; a bare
    # `conflict` string is non-retryable here) — so the agent re-issues the
    # pull unchanged once the upstream task completes.
    if (
        policy is not None
        and policy.require_deps_complete
        and not bypass_gates
        and current_status == "icebox"
        and to_status == "in_progress"
    ):
        pending = incomplete_dependencies(conn, task_id)
        if pending:
            return TransitionResult(
                ok=False,
                task_id=task_id,
                previous_status=current_status,
                new_status=to_status,
                error=(
                    "blocked: prerequisites not complete: "
                    + ", ".join(pending)
                    + " — finish them or pass force=True"
                ),
                error_category="transient",
            )

    # Testing-before-complete gate: in_progress→complete must route
    # through `testing` so the verification choreography runs. The edge
    # stays legal in the state machine (testing→complete and forced
    # paths work); policy just blocks the shortcut.
    skip_testing_warning: str | None = None
    if current_status == "in_progress" and to_status == "complete":
        if policy is not None and policy.block_in_progress_to_complete and not bypass_gates:
            return TransitionResult(
                ok=False,
                task_id=task_id,
                previous_status=current_status,
                new_status=to_status,
                error=(
                    "must pass through testing: move in_progress→testing, run "
                    f"the verification matrix, then testing→complete — "
                    f"`cos task-move {task_id} --to testing`. Override: force=True."
                ),
                error_category="validation",
            )
        # config=None path (tests/migrations): keep the soft warning.
        skip_testing_warning = (
            "convention: in_progress→complete skipped 'testing' — "
            "Core Loop expects move-to-testing → run verification matrix → "
            "task-done. Legal but bypasses the gate; record verification in "
            "the work log if intentional."
        )

    # WIP enforcement, status re-verification, and the row UPDATE all run
    # together inside the atomic BEGIN IMMEDIATE critical section below
    # — the count→write gap and the read→write gap are both inside
    # one write lock, so no concurrent transition can slip between them.
    wip_state: dict[str, int] = {}

    # ── Transition gates (DoR / DoD) ────────────────────
    # Validate the task body against the kind's rules. file_path=None
    # (DB-only mode used by tests/migrations) skips the body gate.
    target_file_for_gate = file_path or (Path(current_file_path) if current_file_path else None)
    gate_warnings: list[str] = []
    gate_override_reason: str | None = None
    gate_override_actor: str | None = None
    if (
        not bypass_gates
        and target_file_for_gate is not None
        and to_status in {"in_progress", "complete"}
    ):
        try:
            from board_os.transition_gates import (
                GatesConfigError,
                load_gates_config,
            )
            from board_os.transition_gates_validator import (
                validate_transition as _gate_validate,
            )

            if target_file_for_gate.exists():
                body_text = target_file_for_gate.read_text(encoding="utf-8")
                kind = _extract_kind_from_frontmatter(body_text) or "feature"
                # DoD inputs: read the .last-verify.json freshness signal
                # via the same helper the CLI uses (avoids drift).
                from board_os.transition_gates_cli import (
                    _has_work_log_entries as _wl,
                    _verify_state as _vs,
                )

                has_recent, age = _vs()
                has_work_log = _wl(body_text)

                gates_config = load_gates_config()
                gate_result = _gate_validate(
                    task_id=task_id,
                    kind=kind,
                    body=body_text,
                    new_status=to_status,
                    config=gates_config,
                    has_recent_verify=has_recent,
                    verify_age_seconds=age,
                    has_work_log=has_work_log,
                    override_reason=os.environ.get("COS_OVERRIDE_REASON"),
                    override_actor=os.environ.get("COS_AGENT") or agent_session,
                    # Task files live at <root>/docs/tasks/<file>; the repo root is
                    # three parents up. Passing it enables the Read First dead-link
                    # check (WARN) — pure validator tests omit it and skip the stat.
                    project_root=str(target_file_for_gate.resolve().parent.parent.parent),
                )

                if gate_result.blocked:
                    return TransitionResult(
                        ok=False,
                        task_id=task_id,
                        previous_status=current_status,
                        new_status=to_status,
                        error=(
                            "transition gate failed: "
                            + "; ".join(f"[{m.code}] {m.message}" for m in gate_result.messages)
                        ),
                        error_category="validation",
                        wip_state=wip_state,
                    )

                # PASS or WARN — collect override metadata for audit.
                for m in gate_result.messages:
                    gate_warnings.append(f"[{m.code}] {m.message}")
                if any("[OVERRIDDEN]" in m.message for m in gate_result.messages):
                    gate_override_reason = os.environ.get("COS_OVERRIDE_REASON")
                    gate_override_actor = os.environ.get("COS_AGENT") or agent_session
        except GatesConfigError as exc:
            # Bad config — surface to retro reviewers but don't crash live work.
            gate_warnings.append(f"transition-gates config error (gate skipped): {exc}")
        except Exception as exc:
            gate_warnings.append(f"transition-gates internal error (skipped): {exc}")

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
    if skip_testing_warning is not None:
        warnings.append(skip_testing_warning)
    warnings.extend(gate_warnings)
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
                    gate_override_reason,
                    gate_override_actor,
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


# ---------- Helpers ----------


def _parse_labels(raw: object) -> set[str]:
    """Normalize a task's labels_json column into a set of label strings.

    Accepts the JSON-array string the DB stores, a real list, or None.
    """
    if not raw:
        return set()
    if isinstance(raw, (list, tuple)):
        return {str(x) for x in raw}
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return set()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return {t.strip() for t in text.split(",") if t.strip()}
        if isinstance(parsed, list):
            return {str(x) for x in parsed}
    return set()


def _extract_kind_from_frontmatter(content: str) -> str | None:
    """Pull `kind:` from YAML frontmatter without dragging in PyYAML.

    Frontmatter lives between two `---` lines at file head. Returns the
    raw value as written; defaults to None when absent or malformed.
    """
    if not content.startswith("---"):
        return None
    end = content.find("\n---", 3)
    if end < 0:
        return None
    head = content[3:end]
    for line in head.splitlines():
        line = line.strip()
        if line.startswith("kind:"):
            return line.split(":", 1)[1].strip().strip('"').strip("'") or None
    return None


def _patch_fm_field(fm_text: str, key: str, value: str) -> str:
    """Replace a scalar field in raw YAML text without touching comments or key order.

    If the key already exists, its value is updated in-place.
    If it is absent, the key is appended on a new line (handles tasks
    created before a field was added to the template).
    """
    import re as _re

    pattern = _re.compile(rf"^({_re.escape(key)}:)[ \t]*.*$", _re.MULTILINE)
    if pattern.search(fm_text):
        return pattern.sub(rf"\1 {value}", fm_text, count=1)
    return fm_text + f"\n{key}: {value}"


def _write_status_to_frontmatter(
    path: Path,
    new_status: str,
    *,
    agent_session: str | None,
) -> None:
    """Atomically update status (+ started/completed timestamps) in frontmatter.

    Uses targeted regex field-patching instead of YAML round-trip so that
    inline comments (e.g. ``# always start here``) are preserved verbatim.
    """
    if not path.exists():
        raise FileNotFoundError(str(path))

    content = path.read_text(encoding="utf-8")
    import re as _re

    fm_re = _re.compile(r"^---\s*\n(.*?)\n---\s*\n", _re.DOTALL)
    m = fm_re.match(content)
    if not m:
        raise ValueError(f"{path}: no frontmatter to update")

    fm_raw = m.group(1)

    # Validate YAML is parseable before touching anything.
    try:
        fm_parsed = yaml.safe_load(fm_raw) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"{path}: frontmatter YAML broken: {exc}") from exc
    if not isinstance(fm_parsed, dict):
        raise ValueError(f"{path}: frontmatter is not a mapping")

    today = time.strftime("%Y-%m-%d")
    fm_raw = _patch_fm_field(fm_raw, "status", new_status)
    if agent_session is not None:
        fm_raw = _patch_fm_field(fm_raw, "agent_session", agent_session)
    if new_status == "in_progress" and not fm_parsed.get("started"):
        fm_raw = _patch_fm_field(fm_raw, "started", today)
    if new_status == "complete" and not fm_parsed.get("completed"):
        fm_raw = _patch_fm_field(fm_raw, "completed", today)

    new_content = f"---\n{fm_raw}\n---\n" + content[m.end() :]

    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=str(path.parent),
        prefix=".task-",
        suffix=".tmp",
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
            fh.write(new_content)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _format_yaml_scalar_token(value: str) -> str:
    """Format a scalar for YAML frontmatter (unquoted id vs JSON-quoted string)."""
    import re as _re

    if _re.match(r"^[a-z0-9][a-z0-9-]*$", value, _re.I):
        return value
    return json.dumps(value)


def patch_task_frontmatter_scalars(path: Path, updates: dict[str, str]) -> None:
    if not updates:
        return
    if not path.exists():
        raise FileNotFoundError(str(path))

    content = path.read_text(encoding="utf-8")
    import re as _re

    fm_re = _re.compile(r"^---\s*\n(.*?)\n---\s*\n", _re.DOTALL)
    m = fm_re.match(content)
    if not m:
        raise ValueError(f"{path}: no frontmatter to update")

    fm_raw = m.group(1)
    try:
        fm_parsed = yaml.safe_load(fm_raw) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"{path}: frontmatter YAML broken: {exc}") from exc
    if not isinstance(fm_parsed, dict):
        raise ValueError(f"{path}: frontmatter is not a mapping")

    for key, raw_val in updates.items():
        token = _format_yaml_scalar_token(raw_val)
        fm_raw = _patch_fm_field(fm_raw, key, token)

    new_content = f"---\n{fm_raw}\n---\n" + content[m.end() :]

    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=str(path.parent),
        prefix=".task-",
        suffix=".tmp",
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
            fh.write(new_content)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
