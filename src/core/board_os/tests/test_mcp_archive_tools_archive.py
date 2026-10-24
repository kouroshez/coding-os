"""Archive drain, reclaim, reconciliation, and the board envelope budget."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from core.board_os import mcp_tools

from .conftest import _backdate_task, _parse


def test_archive_transition_from_icebox(project: Path, conn: sqlite3.Connection):
    """icebox->archive is the terminal drain `cos task-archive` relies on."""
    mcp_tools.cos_task_create(
        conn, title="Drain me", swimlane="core", kind="chore", status="icebox"
    )
    env = _parse(mcp_tools.cos_task_move(conn, task_id="TASK-001", to="archive"))
    assert env["ok"] is True, env
    assert (
        conn.execute("SELECT status FROM tasks WHERE task_id='TASK-001'").fetchone()[0] == "archive"
    )


def test_archive_rejected_from_in_progress(project: Path, conn: sqlite3.Connection):
    """No direct in_progress->archive edge — so `cos task-cancel` parks active work to icebox."""
    mcp_tools.cos_task_create(conn, title="Active", swimlane="core", kind="bug", status="icebox")
    conn.execute("UPDATE tasks SET status='in_progress' WHERE task_id='TASK-001'")
    conn.commit()
    env = _parse(mcp_tools.cos_task_move(conn, task_id="TASK-001", to="archive"))
    assert env["ok"] is False, (
        "in_progress->archive must be rejected (validates cancel's icebox park)"
    )


def _task_file(project: Path, task_id: str) -> Path:
    return next((project / "docs" / "tasks").glob(f"{task_id}-*.md"))


def test_daily_never_archives_an_old_complete_card(project: Path, conn: sqlite3.Connection):
    """Archiving is a deliberate move only — a card's age never retires it."""
    mcp_tools.cos_task_create(conn, title="Done", swimlane="core", kind="chore", status="icebox")
    _backdate_task(conn, "TASK-001", "complete", 400 * 86400)

    assert _parse(mcp_tools.cos_task_daily(conn))["ok"] is True

    assert (
        conn.execute("SELECT status FROM tasks WHERE task_id='TASK-001'").fetchone()[0]
        == "complete"
    )


def test_manual_archive_writes_the_file(project: Path, conn: sqlite3.Connection):
    """A deliberate move keeps file and DB in step."""
    mcp_tools.cos_task_create(conn, title="Drop", swimlane="core", kind="chore", status="icebox")
    env = _parse(mcp_tools.cos_task_move(conn, task_id="TASK-001", to="archive"))
    assert env["ok"] is True, env
    assert "status: archive" in _task_file(project, "TASK-001").read_text(encoding="utf-8")


def test_reclaim_without_session_attributes_to_system_actor(
    project: Path, conn: sqlite3.Connection
):
    """An unattended reclaim (no session) is system-, not human-attributed."""
    env = _parse(
        mcp_tools.cos_task_create(
            conn,
            title="Zombie",
            swimlane="core",
            kind="chore",
            outcome="zombie reclaim attribution guard outcome.",
            ready=True,
        )
    )
    tid = env["data"]["task_id"]
    assert _parse(
        mcp_tools.cos_task_move(conn, task_id=tid, to="in_progress", agent_session="ses-dead")
    )["ok"]
    old = int(time.time()) - 48 * 3600
    conn.execute("UPDATE tasks SET started_at=? WHERE task_id=?", (old, tid))
    conn.execute("UPDATE task_status_history SET transitioned_at=? WHERE task_id=?", (old, tid))
    conn.commit()
    rec = _parse(mcp_tools.cos_task_reclaim(conn))
    assert tid in [r["task_id"] for r in rec["data"]["reclaimed"]]
    session = conn.execute(
        "SELECT agent_session FROM task_status_history "
        "WHERE task_id=? AND new_status='icebox' ORDER BY id DESC LIMIT 1",
        (tid,),
    ).fetchone()[0]
    assert session == "ses-system-reclaim"


def test_reclaim_covers_hub_human_actor_zombie(project: Path, conn: sqlite3.Connection):
    """A hub drag-to-in_progress (human actor, no agent presence file) is hookless,
    but the reclaim sweep is actor-agnostic — owner-without-presence counts as
    inactive, so the zombie is recovered. Locks the MISS-1 coverage that F2a+F2b
    provide without a parallel hub-side code path."""
    mcp_tools.cos_task_create(
        conn, title="Hub-created", swimlane="core", kind="bug", status="icebox"
    )
    old = int(time.time()) - 30 * 3600  # > 24h in_progress window
    conn.execute(
        "UPDATE tasks SET status='in_progress', agent_session='human:webuser', started_at=? "
        "WHERE task_id='TASK-001'",
        (old,),
    )
    conn.execute(
        "UPDATE task_status_history SET transitioned_at=? WHERE task_id='TASK-001'", (old,)
    )
    conn.commit()
    env = _parse(mcp_tools.cos_task_reclaim(conn))
    assert any(r["task_id"] == "TASK-001" for r in env["data"]["reclaimed"]), (
        "a hub/human zombie with no agent presence must be reclaimable"
    )


def test_reclaim_skips_likely_complete_testing(project: Path, conn: sqlite3.Connection):
    """The auto-reclaim sweep must NOT recycle a likely-complete testing task — leave it for review."""
    mcp_tools.cos_task_create(conn, title="Finished", swimlane="core", kind="bug", status="icebox")
    _backdate_task(conn, "TASK-001", "testing", 8 * 3600)
    conn.execute("UPDATE tasks SET work_log_last_5=? WHERE task_id='TASK-001'", ('["did it"]',))
    conn.commit()
    env = _parse(mcp_tools.cos_task_reclaim(conn))
    assert any(s["task_id"] == "TASK-001" for s in env["data"]["skipped_for_review"])
    assert not any(r["task_id"] == "TASK-001" for r in env["data"]["reclaimed"])
    assert (
        conn.execute("SELECT status FROM tasks WHERE task_id='TASK-001'").fetchone()[0] == "testing"
    )
