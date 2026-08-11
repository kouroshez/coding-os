"""Tests for core.board_os.mcp_tools — L.3 MCP surface."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from core.board_os import mcp_tools

from .conftest import _parse


def test_task_edit_swaps_fresh_work_log_and_skips_phantom_body_edit(
    project: Path, conn: sqlite3.Connection
):
    """TASK-773/775/787: the board drawer body is a snapshot. cos_task_edit swaps
    in the FRESH on-disk Work Log (a concurrent cos_work_log_append is never lost)
    and records no phantom body edit when only the stripped H1 differs."""
    created = _parse(
        mcp_tools.cos_task_create(
            conn,
            title="Has a work log",
            swimlane="core",
            kind="feature",
            outcome="A task whose body carries a Work Log.",
        )
    )
    task_id = created["data"]["task_id"]
    file_path = project / created["data"]["file_path"]

    mcp_tools.cos_work_log_append(conn, task_id=task_id, summary="first checkpoint")

    # The drawer snapshots the body H1-stripped (like editBody), Work Log = [first].
    snapshot = re.sub(
        r"^\s*#\s+.+\n+",
        "",
        file_path.read_text(encoding="utf-8").split("---", 2)[2].lstrip("\n"),
    )
    # A concurrent agent appends a second line AFTER the snapshot.
    mcp_tools.cos_work_log_append(conn, task_id=task_id, summary="second (concurrent)")

    # Saving the stale snapshot: only the stripped H1 differs → no phantom body
    # edit, and the concurrent line is swapped in (not overwritten).
    r1 = _parse(mcp_tools.cos_task_edit(conn, task_id=task_id, body=snapshot))
    assert r1["ok"] is True
    assert "body" not in r1["data"]["changed"]
    after = file_path.read_text(encoding="utf-8")
    assert "second (concurrent)" in after  # fresh log survived the save
    assert "first checkpoint" in after

    # A real spec edit IS recorded and keeps the fresh Work Log in place.
    edited = snapshot.replace("A task whose body carries a Work Log.", "Edited outcome.")
    r2 = _parse(mcp_tools.cos_task_edit(conn, task_id=task_id, body=edited))
    assert "body" in r2["data"]["changed"]
    after2 = file_path.read_text(encoding="utf-8")
    assert "Edited outcome." in after2
    assert "second (concurrent)" in after2


def test_task_show_returns_frontmatter_and_body(project: Path, conn: sqlite3.Connection):
    created = _parse(
        mcp_tools.cos_task_create(
            conn,
            title="Show me",
            swimlane="core",
            kind="feature",
            outcome="A task to display.",
        )
    )
    task_id = created["data"]["task_id"]

    env = _parse(mcp_tools.cos_task_show(conn, task_id=task_id))
    assert env["ok"] is True
    data = env["data"]
    assert data["id"] == task_id
    assert data["title"] == "Show me"
    assert data["status"] == "icebox"
    assert data["body"] is not None
    assert "Show me" in data["body"]
    assert data["file_path"].endswith(".md")


def test_task_show_omits_body_when_disabled(project: Path, conn: sqlite3.Connection):
    created = _parse(
        mcp_tools.cos_task_create(conn, title="No body", swimlane="core", kind="feature")
    )
    env = _parse(
        mcp_tools.cos_task_show(conn, task_id=created["data"]["task_id"], include_body=False)
    )
    assert env["ok"] is True
    assert env["data"]["body"] is None


def test_task_show_not_found(project: Path, conn: sqlite3.Connection):
    env = _parse(mcp_tools.cos_task_show(conn, task_id="TASK-999"))
    assert env["ok"] is False
    assert env["error"]["category"] == "not_found"


def test_create_skeleton_surfaces_dor_gaps_in_envelope(project: Path, conn: sqlite3.Connection):
    """A lean create (no acceptance, not ready) must succeed but announce its
    own incompleteness — dor.gaps lists the placeholder codes and dor.fix
    tells the agent the exact next moves (TASK-339)."""
    env = _parse(
        mcp_tools.cos_task_create(
            conn,
            title="Skeleton capture",
            swimlane="core",
            kind="feature",
            outcome="Some outcome sentence that is long enough.",
        )
    )
    assert env["ok"] is True
    dor = env["data"]["dor"]
    assert dor["ready"] is False
    codes = {g["code"] for g in dor["gaps"]}
    assert any(c.startswith("DOR_ACCEPTANCE") for c in codes)
    assert "task-ready" in dor["fix"]


def test_create_one_shot_reports_clean_dor(project: Path, conn: sqlite3.Connection):
    """A fully-formed one-shot create (outcome + acceptance + ready) reports
    dor.ready=true with zero gaps and no fix hint."""
    env = _parse(
        mcp_tools.cos_task_create(
            conn,
            title="Fully groomed task",
            swimlane="core",
            kind="feature",
            outcome="Board renders agent chips from manifest data end to end.",
            acceptance=(
                "- **Given** a manifest agent, **When** it emits an event, "
                "**Then** the chip uses manifest data.\n"
                "- **Given** the suite, **When** run, **Then** green."
            ),
            read_first=["docs/tasks"],
            ready=True,
        )
    )
    assert env["ok"] is True
    dor = env["data"]["dor"]
    assert dor["ready"] is True
    assert dor["gaps"] == []
    assert "fix" not in dor


def test_create_in_progress_blocks_without_dor(project: Path, conn: sqlite3.Connection):
    """Creating directly into in_progress runs the DoR gate (parity with the
    icebox→in_progress transition). A feature with a placeholder body must be
    rejected — the agent cannot start undefined work."""
    env = _parse(
        mcp_tools.cos_task_create(
            conn,
            title="Undefined feature started directly",
            swimlane="core",
            kind="feature",
            status="in_progress",
        )
    )
    assert env["ok"] is False
    assert env["error"]["category"] == "validation"
    assert "Definition of Ready" in env["error"]["message"]


def test_create_in_progress_passes_with_outcome_and_acceptance(
    project: Path, conn: sqlite3.Connection
):
    """One-shot create-and-start works when the caller supplies a real
    Outcome + Acceptance (G/W/T); the acceptance is threaded into the body."""
    env = _parse(
        mcp_tools.cos_task_create(
            conn,
            title="Well-defined feature",
            swimlane="core",
            kind="feature",
            status="in_progress",
            outcome="Add OAuth login that issues 24h JWTs with refresh rotation.",
            acceptance=(
                "- **Given** a logged-out user with valid credentials\n"
                "- **When** they sign in\n"
                "- **Then** a 24h JWT plus refresh token are issued."
            ),
        )
    )
    assert env["ok"] is True
    content = (project / env["data"]["file_path"]).read_text(encoding="utf-8")
    assert "24h JWT plus refresh token" in content


def test_create_icebox_lean_capture_allowed(project: Path, conn: sqlite3.Connection):
    """Lean capture into icebox stays unrestricted — the DoR gate only fires
    on entry to in_progress, not on backlog capture."""
    env = _parse(
        mcp_tools.cos_task_create(
            conn,
            title="Rough idea captured for later",
            swimlane="core",
            kind="feature",
        )
    )
    assert env["ok"] is True
    assert env["data"]["status"] == "icebox"
