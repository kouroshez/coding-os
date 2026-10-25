"""cos_task_move, pick, wip, work-log, daily and retro."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from core.board_os import mcp_tools

from .conftest import _parse


def test_move_happy_path(project: Path, conn: sqlite3.Connection):
    _parse(
        mcp_tools.cos_task_create(
            conn,
            title="move me",
            swimlane="core",
            kind="feature",
        )
    )
    # icebox → in_progress (no dedicated "ready" column any more).
    # force=True bypasses the DoR body gate; this test exercises
    # transition mechanics, not body validation (covered by
    # test_transition_gates_validator.py).
    env = _parse(
        mcp_tools.cos_task_move(
            conn,
            task_id="TASK-001",
            to="in_progress",
            force=True,
        )
    )
    assert env["ok"] is True
    assert env["data"]["previous_status"] == "icebox"
    assert env["data"]["new_status"] == "in_progress"


def test_reposition_swimlane_only(project: Path, conn: sqlite3.Connection):
    _parse(
        mcp_tools.cos_task_create(
            conn,
            title="lane test",
            swimlane="core",
            kind="feature",
        )
    )
    env = _parse(
        mcp_tools.cos_task_reposition(
            conn,
            task_id="TASK-001",
            swimlane="docs",
        )
    )
    assert env["ok"] is True
    assert env["data"]["new_swimlane"] == "docs"
    row = conn.execute(
        "SELECT swimlane FROM tasks WHERE task_id = ?",
        ("TASK-001",),
    ).fetchone()
    assert row[0] == "docs"


def test_reposition_status_and_swimlane(project: Path, conn: sqlite3.Connection):
    _parse(
        mcp_tools.cos_task_create(
            conn,
            title="both",
            swimlane="core",
            kind="chore",
        )
    )
    env = _parse(
        mcp_tools.cos_task_reposition(
            conn,
            task_id="TASK-001",
            to="in_progress",
            swimlane="docs",
            force=True,  # bypass DoR — mechanics test
        )
    )
    assert env["ok"] is True
    assert env["data"]["new_status"] == "in_progress"
    assert env["data"]["new_swimlane"] == "docs"
    row = conn.execute(
        "SELECT status, swimlane FROM tasks WHERE task_id = ?",
        ("TASK-001",),
    ).fetchone()
    assert row[0] == "in_progress"
    assert row[1] == "docs"


def test_move_wip_cap_rejection(project: Path, conn: sqlite3.Connection):
    # cap=2 per fixture; make 2 in_progress then try 3rd.
    for i in range(3):
        mcp_tools.cos_task_create(
            conn,
            title=f"t{i}",
            swimlane="core",
            kind="chore",
        )
    # bypass_gates skips DoR body validation (chore default body has
    # placeholder Outcome) but keeps WIP enforcement active so the
    # third move legitimately hits the cap.
    for tid in ("TASK-001", "TASK-002"):
        mcp_tools.cos_task_move(
            conn,
            task_id=tid,
            to="in_progress",
            bypass_gates=True,
        )
    env = _parse(
        mcp_tools.cos_task_move(
            conn,
            task_id="TASK-003",
            to="in_progress",
            bypass_gates=True,
        )
    )
    assert env["ok"] is False
    assert "WIP cap" in env["error"]["message"]


def test_move_to_complete_blocks_when_file_missing(project: Path, conn: sqlite3.Connection):
    # a complete-transition must fail CLOSED when the DB names a file
    # that is absent on disk — otherwise the DoD gate is silently skipped and an
    # unverifiable task closes (the 523/524/525 desync).
    _parse(mcp_tools.cos_task_create(conn, title="ghost", swimlane="core", kind="chore"))
    mcp_tools.cos_task_move(conn, task_id="TASK-001", to="in_progress", force=True)
    mcp_tools.cos_task_move(conn, task_id="TASK-001", to="testing", force=True)
    row = conn.execute("SELECT file_path FROM tasks WHERE task_id='TASK-001'").fetchone()
    (project / row[0]).unlink()  # file desyncs from the DB
    env = _parse(mcp_tools.cos_task_move(conn, task_id="TASK-001", to="complete"))
    assert env["ok"] is False
    assert env["error"]["category"] == "validation"
    assert "task file not found" in env["error"]["message"]


def test_move_to_complete_force_overrides_missing_file(project: Path, conn: sqlite3.Connection):
    # --force is the audited escape hatch — a missing file still closes under force.
    _parse(mcp_tools.cos_task_create(conn, title="ghost2", swimlane="core", kind="chore"))
    mcp_tools.cos_task_move(conn, task_id="TASK-001", to="in_progress", force=True)
    mcp_tools.cos_task_move(conn, task_id="TASK-001", to="testing", force=True)
    row = conn.execute("SELECT file_path FROM tasks WHERE task_id='TASK-001'").fetchone()
    (project / row[0]).unlink()
    env = _parse(mcp_tools.cos_task_move(conn, task_id="TASK-001", to="complete", force=True))
    assert env["ok"] is True


def test_pick_returns_ready_tasks(project: Path, conn: sqlite3.Connection):
    """Candidates are icebox tasks carrying the 'ready' label (plus emergency)."""
    mcp_tools.cos_task_create(
        conn,
        title="low",
        swimlane="core",
        kind="chore",
        priority="P3",
        labels=["ready"],
    )
    mcp_tools.cos_task_create(
        conn,
        title="high",
        swimlane="core",
        kind="feature",
        priority="P0",
        labels=["ready"],
    )

    env = _parse(mcp_tools.cos_task_pick(conn))
    assert env["ok"] is True
    candidates = env["data"]["candidates"]
    assert len(candidates) >= 1
    # P0 should be first.
    assert candidates[0]["priority"] == "P0"


def test_wip_check(project: Path, conn: sqlite3.Connection):
    env = _parse(mcp_tools.cos_task_wip_check(conn))
    assert env["ok"] is True
    assert env["data"]["counts"]["in_progress"] == 0
    assert env["data"]["caps"]["in_progress"] == 2
    assert env["data"]["over_cap"] is False
