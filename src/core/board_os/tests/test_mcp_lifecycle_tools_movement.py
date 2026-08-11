"""cos_task_move, the learning-loop close, pick, wip, work-log, daily and retro."""

from __future__ import annotations

import os
import sqlite3
import time
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
    # TASK-532: a complete-transition must fail CLOSED when the DB names a file
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


def _seed_panel_recall(project: Path, conn: sqlite3.Connection, *, session: str):
    """Panel dir with a surfaced lesson + a recurring friction observation.

    Returns (panel_dir, pattern_id). The friction cluster key is a contiguous
    substring of the lesson, so it validates as NOT helpful (recurred)."""
    panel = project / ".coding-os" / "claude" / "panels" / "p1"
    panel.mkdir(parents=True)
    (panel / "session-id").write_text(session, encoding="utf-8")
    (panel / ".thinking_os-gate").write_text(f"{session} COMPLICATED 2", encoding="utf-8")
    lesson = (
        "Recurring block (3x): enforce-commit-message commit-msg-contract on a bad "
        "commit title -> rewrite the title"
    )
    conn.execute(
        "INSERT INTO learned_patterns (pattern, memory_type, confidence) VALUES (?, 'lesson', 0.6)",
        (lesson,),
    )
    pid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT INTO observations (session_id, tool_name, observation_type, memory_type, "
        "impact_score, title, narrative, content_hash) "
        "VALUES (?, 'Bash', 'hook_block', 'hook_block', 0.6, 'blocked', "
        "'enforce-commit-message commit-msg-contract on a bad commit title', 'cll1')",
        (session,),
    )
    conn.commit()
    sugg = panel / ".learn-suggestions"
    sugg.write_text(f"{pid}\t{lesson}\n", encoding="utf-8")
    old = time.time() - 120
    os.utime(sugg, (old, old))
    return panel, pid


def test_close_learning_loop_validates_on_mcp_path(project, conn, monkeypatch):
    # The MCP server has no COS_PANEL_DIR (the Bash hook that owns closure never
    # fires there), so this path must close the loop itself.
    monkeypatch.setenv("COS_STATE_DIR", str(project / ".coding-os"))
    monkeypatch.setenv("COS_AGENT", "claude")
    monkeypatch.delenv("COS_PANEL_DIR", raising=False)
    panel, pid = _seed_panel_recall(project, conn, session="ses-close-mcp")

    mcp_tools._close_learning_loop_safe(conn)

    validations = conn.execute("SELECT COUNT(*) FROM pattern_validations").fetchone()[0]
    tv, tvio = conn.execute(
        "SELECT times_validated, times_violated FROM learned_patterns WHERE id=?", (pid,)
    ).fetchone()
    assert validations == 1, "surfaced lesson must be validated on the MCP path"
    assert tvio == 1 and tv == 0, "recurred lesson validates as not-helpful"
    assert (panel / ".learn-suggestions").stat().st_size == 0, "per-task boundary: cleared"


def test_close_learning_loop_noop_when_panel_dir_set(project, conn, monkeypatch):
    # COS_PANEL_DIR set == a shell ran the CLI; the Bash hook owns closure, so
    # this path must skip to avoid double-validating.
    monkeypatch.setenv("COS_STATE_DIR", str(project / ".coding-os"))
    monkeypatch.setenv("COS_AGENT", "claude")
    panel, _pid = _seed_panel_recall(project, conn, session="ses-close-cli")
    monkeypatch.setenv("COS_PANEL_DIR", str(panel))

    mcp_tools._close_learning_loop_safe(conn)

    validations = conn.execute("SELECT COUNT(*) FROM pattern_validations").fetchone()[0]
    assert validations == 0, "must skip when COS_PANEL_DIR is set (Bash hook owns it)"
    assert (panel / ".learn-suggestions").stat().st_size > 0, "file left for the Bash hook"


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
