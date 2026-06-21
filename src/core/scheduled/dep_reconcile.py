"""Dependency-readiness reconciler (CRON A task).

Closes the gaps the per-completion cascade (board_os.cascade_ready_dependents)
cannot cover, because that cascade only fires at the instant ONE dependency
transitions to ``complete``:

(a) re-block — a ready/icebox task whose dependency was reverted out of
    ``complete`` is moved back to ``blocked`` with a reason naming the reopened
    dependency;
(b) needs-authoring — a task now dependency-unblocked but with an incomplete
    Definition-of-Ready body is surfaced (reusing cascade_ready_dependents over
    every complete task, not re-implemented);
(c) long-blocked — a task blocked beyond a day threshold is surfaced for human
    review.

See docs/engineering/scheduled-jobs.md for the full contract.
"""

from __future__ import annotations

import json
import sqlite3
import time

DEFAULT_BLOCKED_REVIEW_DAYS = 14


def _reblock_reopened(conn: sqlite3.Connection, *, dry_run: bool) -> list[dict]:
    """Move ready/icebox tasks back to blocked when a dependency left 'complete'."""
    from board_os.mcp_tools import (
        READY_LABEL,
        _labels_list_from_json,
        cos_task_move,
    )
    from board_os.workflow import incomplete_dependencies

    rows = conn.execute("SELECT task_id, labels_json FROM tasks WHERE status = 'icebox'").fetchall()

    reblocked: list[dict] = []
    for task_id, labels_json in rows:
        if READY_LABEL not in _labels_list_from_json(labels_json):
            continue
        pending = incomplete_dependencies(conn, str(task_id))
        if not pending:
            continue
        reason = f"dependency reopened — re-blocked: waiting on {', '.join(pending)}"
        entry = {"task_id": str(task_id), "reason": reason, "pending": pending}
        if not dry_run:
            # icebox→blocked is not a state-machine edge (valid from icebox:
            # in_progress/emergency/archive), so force the deliberate re-block.
            env = json.loads(
                cos_task_move(conn, task_id=str(task_id), to="blocked", reason=reason, force=True)
            )
            if not env.get("ok"):
                entry["move_failed"] = env.get("error")
        reblocked.append(entry)
    return reblocked


def _surface_unblocked(conn: sqlite3.Connection, *, dry_run: bool) -> dict[str, list]:
    """Reuse cascade_ready_dependents over every complete task to re-classify
    its dependents — aggregating those auto-readied vs. still needs-authoring."""
    from board_os.mcp_tools import cascade_ready_dependents

    complete_ids = [
        str(r[0])
        for r in conn.execute("SELECT task_id FROM tasks WHERE status = 'complete'").fetchall()
    ]

    readied: list[str] = []
    needs_authoring: list[dict] = []
    seen_authoring: set[str] = set()
    for completed_id in complete_ids:
        if dry_run:
            # The cascade mutates (auto-ready); a dry run must not. Counts for
            # this branch are intentionally omitted rather than re-implemented.
            continue
        report = cascade_ready_dependents(conn, completed_id)
        readied.extend(report.get("readied", []))
        for item in report.get("needs_authoring", []):
            tid = item.get("task_id")
            if tid and tid not in seen_authoring:
                seen_authoring.add(tid)
                needs_authoring.append(item)
    return {"readied": readied, "needs_authoring": needs_authoring}


def _surface_long_blocked(conn: sqlite3.Connection, *, review_days: int) -> list[dict]:
    """Surface tasks blocked longer than review_days for human review (read-only)."""
    now = int(time.time())
    cutoff = now - review_days * 86400
    rows = conn.execute(
        "SELECT task_id, "
        "  (SELECT MAX(transitioned_at) FROM task_status_history h "
        "   WHERE h.task_id = tasks.task_id AND h.new_status = 'blocked') "
        "FROM tasks WHERE status = 'blocked'"
    ).fetchall()

    surfaced: list[dict] = []
    for task_id, blocked_at in rows:
        if blocked_at is None or int(blocked_at) > cutoff:
            continue
        blocked_days = (now - int(blocked_at)) // 86400
        surfaced.append({"task_id": str(task_id), "blocked_days": blocked_days})
    return surfaced


def run_dep_reconcile(
    conn: sqlite3.Connection,
    *,
    dry_run: bool,
    blocked_review_days: int = DEFAULT_BLOCKED_REVIEW_DAYS,
) -> dict:
    """Run all three reconciler branches over the whole task graph."""
    if (
        conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='tasks'").fetchone()
        is None
    ):
        return {"status": "skipped", "reason": "tasks table not present"}

    reblocked = _reblock_reopened(conn, dry_run=dry_run)
    unblocked = _surface_unblocked(conn, dry_run=dry_run)
    long_blocked = _surface_long_blocked(conn, review_days=blocked_review_days)

    if not dry_run:
        conn.commit()

    return {
        "status": "ok",
        "reblocked": reblocked,
        "readied": unblocked["readied"],
        "needs_authoring": unblocked["needs_authoring"],
        "long_blocked": long_blocked,
        "dry_run": dry_run,
    }
