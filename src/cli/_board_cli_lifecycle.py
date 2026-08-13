"""Task lifecycle commands: create, move, start, ready, reclaim, done, block, cancel, archive."""

from __future__ import annotations

import sys

import click

from cli._board_cli_outcome import _record_brain_outcome_safe
from cli._board_cli_shared import (
    _agent_session_id,
    _db_conn,
    _parse_envelope,
    _print_envelope,
)

# ---------------------------------------------------------------------------
# task-create / task-move / task-start / task-done / task-block / task-cancel
# ---------------------------------------------------------------------------


@click.command("task-create", help="Create a new Scrumban task (lean template).")
@click.option("--title", required=True)
@click.option("--swimlane", required=True)
@click.option(
    "--kind",
    required=True,
    type=click.Choice(["feature", "bug", "chore", "spike", "docs", "refactor", "test", "security"]),
)
@click.option("--priority", default="P2", type=click.Choice(["P0", "P1", "P2", "P3"]))
@click.option("--appetite", default="1d")
@click.option("--epic", default=None)
@click.option("--labels", default="", help="Comma-separated free tags")
@click.option("--outcome", default=None, help="One measurable sentence — the task's goal.")
@click.option(
    "--acceptance",
    default=None,
    help="Acceptance G/W/T markdown (e.g. '- **Given** ...\\n- **When** ...\\n- **Then** ...'). "
    "Required to start feature/bug/refactor/test/security tasks.",
)
@click.option(
    "--read-first",
    multiple=True,
    help="Doc path(s) for the Read First section — repeatable and/or comma-separated. "
    "(Was a single comma-only flag; repeating it silently kept only the last value.)",
)
@click.option("--depends-on", default="", help="Comma-separated TASK-IDs")
@click.option("--ready", is_flag=True, default=False, help="Mark the task pullable in one shot.")
def task_create_cmd(
    title,
    swimlane,
    kind,
    priority,
    appetite,
    epic,
    labels,
    outcome,
    acceptance,
    read_first,
    depends_on,
    ready,
):
    from board_os import mcp_tools

    conn = _db_conn()
    try:
        envelope = mcp_tools.cos_task_create(
            conn,
            title=title,
            swimlane=swimlane,
            kind=kind,
            priority=priority,
            appetite=appetite,
            epic=epic,
            labels=[label.strip() for label in labels.split(",") if label.strip()],
            outcome=outcome,
            acceptance=acceptance,
            read_first=[p.strip() for chunk in read_first for p in chunk.split(",") if p.strip()]
            or None,
            depends_on=[d.strip() for d in depends_on.split(",") if d.strip()],
            ready=ready,
            agent_session=_agent_session_id(),
        )
    finally:
        conn.close()
    sys.exit(_print_envelope(envelope))


@click.command("task-move")
@click.argument("task_id")
@click.option("--to", required=True)
@click.option("--reason", default=None)
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Override WIP caps AND state-machine validation "
    "(e.g. archive → in_progress after an accidental archive).",
)
def task_move_cmd(task_id, to, reason, force):
    from board_os import mcp_tools

    conn = _db_conn()
    try:
        envelope = mcp_tools.cos_task_move(
            conn,
            task_id=task_id,
            to=to,
            reason=reason or "cli:task-move (no --reason given)",
            bypass_wip=force,
            force=force,
            agent_session=_agent_session_id(),
        )
    finally:
        conn.close()
    sys.exit(_print_envelope(envelope))


def _simple_move(task_id: str, to: str, *, reason: str | None = None, force: bool = False):
    from board_os import mcp_tools

    conn = _db_conn()
    try:
        envelope = mcp_tools.cos_task_move(
            conn,
            task_id=task_id,
            to=to,
            reason=reason,
            bypass_wip=force,
            agent_session=_agent_session_id(),
        )
    finally:
        conn.close()
    sys.exit(_print_envelope(envelope))


@click.command(
    "task-reconcile",
    help="Review stranded tasks with completion evidence — recommends complete/resume/park (read-only).",
)
@click.option(
    "--include-active",
    is_flag=True,
    default=False,
    help="Also review tasks whose owner session is still active.",
)
def task_reconcile_cmd(include_active):
    from board_os import mcp_tools

    conn = _db_conn()
    try:
        envelope = mcp_tools.cos_task_reconcile(conn, include_active=include_active)
    finally:
        conn.close()
    env = _parse_envelope(envelope)
    if not env["ok"]:
        click.echo(f"ERROR: {env['error']['message']}", err=True)
        sys.exit(1)
    data = env["data"]
    s = data["summary"]
    click.echo(
        f"\n  Stranded tasks: {data['count']}  "
        f"(likely-complete {s['likely_complete']} · "
        f"likely-abandoned {s['likely_abandoned']} · needs-review {s['needs_review']})"
    )
    for it in data["stranded"]:
        commits = it["commits_referencing"]
        commits_str = "?" if commits is None else commits
        click.echo(
            f"\n  {it['task_id']} [{it['status']} {it['status_dwell_human']}] "
            f"→ {it['classification']}  ({commits_str} commit(s))"
        )
        click.echo(f"      {it['recommendation']}")
    click.echo()


def _current_status(task_id: str) -> str | None:
    conn = _db_conn()
    try:
        row = conn.execute("SELECT status FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
    finally:
        conn.close()
    return row[0] if row else None


@click.command("task-start")
@click.argument("task_id")
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Override the WIP cap only. Readiness + Definition-of-Ready stay enforced; "
    "set COS_DOR_OVERRIDE=1 with COS_OVERRIDE_REASON to bypass the gate.",
)
def task_start_cmd(task_id, force):
    _simple_move(task_id, "in_progress", force=force)


@click.command("task-ready", help="Toggle the 'ready' label that gates icebox→in_progress.")
@click.argument("task_id")
@click.option(
    "--off", is_flag=True, default=False, help="Remove the ready label instead of adding it."
)
def task_ready_cmd(task_id, off):
    from board_os import mcp_tools

    conn = _db_conn()
    try:
        envelope = mcp_tools.cos_task_ready(
            conn,
            task_id=task_id,
            ready=not off,
            agent_session=_agent_session_id(),
        )
    finally:
        conn.close()
    sys.exit(_print_envelope(envelope))


@click.command(
    "task-reclaim", help="Reclaim zombie in_progress tasks (idle + owner inactive) to icebox+ready."
)
@click.option(
    "--idle-hours", type=int, default=0, help="Override the idle threshold (0 = config default)."
)
@click.option("--dry-run", is_flag=True, default=False, help="List candidates without moving them.")
def task_reclaim_cmd(idle_hours, dry_run):
    from board_os import mcp_tools

    conn = _db_conn()
    try:
        envelope = mcp_tools.cos_task_reclaim(
            conn,
            idle_hours=idle_hours or None,
            dry_run=dry_run,
            agent_session=_agent_session_id(),
        )
    finally:
        conn.close()
    sys.exit(_print_envelope(envelope))


@click.command("task-done")
@click.argument("task_id")
def task_done_cmd(task_id):
    from board_os import mcp_tools

    conn = _db_conn()
    try:
        envelope = mcp_tools.cos_task_move(
            conn,
            task_id=task_id,
            to="complete",
            agent_session=_agent_session_id(),
        )
        parsed = _parse_envelope(envelope)
        if parsed.get("ok"):
            # Codex sessions can bypass Claude's post-write Work Log hook.
            # Record one deterministic completion line in the task markdown.
            mcp_tools.cos_work_log_append(
                conn,
                task_id=task_id,
                summary="Status transitioned to complete via cos task-done.",
                agent_session=_agent_session_id(),
                source="task-done",
            )
            _record_brain_outcome_safe(conn, task_id)
    finally:
        conn.close()
    sys.exit(_print_envelope(envelope))


@click.command("task-block")
@click.argument("task_id")
@click.option("--reason", required=True)
def task_block_cmd(task_id, reason):
    _simple_move(task_id, "blocked", reason=reason)


@click.command("task-cancel")
@click.argument("task_id")
@click.option("--reason", default=None)
@click.option(
    "--park",
    is_flag=True,
    default=False,
    help="Soft-cancel: park in icebox instead of archiving (keeps it in the backlog).",
)
def task_cancel_cmd(task_id, reason, park):
    # Default cancel now DRAINS the board: a terminal-eligible task (icebox /
    # complete) goes to the terminal `archive` sink instead of back to icebox
    # where it would rot. Active work (in_progress / testing /
    # blocked) parks in icebox since the state machine has no direct edge from
    # those states to archive. --park forces the soft icebox cancel everywhere.
    note = f"cancelled: {reason or 'no reason given'}"
    if park:
        _simple_move(task_id, "icebox", reason=note)
        return
    dest = "archive" if _current_status(task_id) in ("icebox", "complete") else "icebox"
    _simple_move(task_id, dest, reason=note)


@click.command(
    "task-archive",
    help="Move a task to the terminal `archive` status (drains icebox/complete off the board).",
)
@click.argument("task_id")
@click.option("--reason", default=None)
def task_archive_cmd(task_id, reason):
    _simple_move(task_id, "archive", reason=f"archived: {reason or 'no reason given'}")
