"""Tests for core.board_os.mcp_tools — L.3 MCP surface."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from core.board_os import mcp_tools

from .conftest import _parse


def test_board_empty(project: Path, conn: sqlite3.Connection):
    env = _parse(mcp_tools.cos_task_board(conn))
    assert env["ok"] is True
    assert env["data"]["count"] == 0
    assert env["data"]["cards"] == []
    assert env["data"]["wip"]["counts"]["in_progress"] == 0


def test_board_with_tasks(project: Path, conn: sqlite3.Connection):
    mcp_tools.cos_task_create(
        conn,
        title="one",
        swimlane="core",
        kind="feature",
    )
    mcp_tools.cos_task_create(
        conn,
        title="two",
        swimlane="docs",
        kind="docs",
    )
    env = _parse(mcp_tools.cos_task_board(conn))
    assert env["ok"] is True
    assert env["data"]["count"] == 2
    swimlanes = {c["swimlane"] for c in env["data"]["cards"]}
    assert "core" in swimlanes
    assert "docs" in swimlanes


def test_board_filters_by_swimlane(project: Path, conn: sqlite3.Connection):
    mcp_tools.cos_task_create(
        conn,
        title="a",
        swimlane="core",
        kind="feature",
    )
    mcp_tools.cos_task_create(
        conn,
        title="b",
        swimlane="docs",
        kind="docs",
    )
    env = _parse(mcp_tools.cos_task_board(conn, swimlane="core"))
    assert env["data"]["count"] == 1
    assert env["data"]["cards"][0]["swimlane"] == "core"


def _insert_complete(
    conn: sqlite3.Connection,
    task_id: str,
    completed_at: int | None,
    *,
    status: str = "complete",
    swimlane: str = "core",
) -> None:
    conn.execute(
        "INSERT INTO tasks (task_id, title, status, file_path, content_hash, mtime, "
        "swimlane, priority, completed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            task_id,
            task_id,
            status,
            f"docs/tasks/{task_id}.md",
            "h",
            0,
            swimlane,
            "P2",
            completed_at,
        ),
    )
    conn.commit()


def test_board_keyset_paginates_complete(project: Path, conn: sqlite3.Connection):
    for i in range(7):
        _insert_complete(conn, f"TASK-9{i:02d}", completed_at=1000 + i)

    env = _parse(
        mcp_tools.cos_task_board(conn, status_filter=["complete"], page_size=3, apply_budget=False)
    )
    col = env["data"]["columns"]["complete"]
    assert col["total_count"] == 7
    assert col["returned"] == 3
    assert col["next_cursor"]
    page1 = [c["id"] for c in env["data"]["cards"]]
    assert page1 == ["TASK-906", "TASK-905", "TASK-904"]  # newest completed first

    env2 = _parse(
        mcp_tools.cos_task_board(
            conn,
            status_filter=["complete"],
            page_size=3,
            cursor=col["next_cursor"],
            apply_budget=False,
        )
    )
    page2 = [c["id"] for c in env2["data"]["cards"]]
    assert page2 == ["TASK-903", "TASK-902", "TASK-901"]
    assert not set(page1) & set(page2)  # no overlap across pages


def test_board_keyset_full_walk_no_dupes(project: Path, conn: sqlite3.Connection):
    for i in range(10):
        _insert_complete(conn, f"TASK-8{i:02d}", completed_at=500 + i)
    seen: list[str] = []
    cursor = None
    for _ in range(20):
        env = _parse(
            mcp_tools.cos_task_board(
                conn, status_filter=["complete"], page_size=4, cursor=cursor, apply_budget=False
            )
        )
        seen.extend(c["id"] for c in env["data"]["cards"])
        cursor = env["data"]["columns"]["complete"]["next_cursor"]
        if not cursor:
            break
    assert len(seen) == 10
    assert len(set(seen)) == 10  # every row exactly once


def test_board_archive_keyset_null_completed(project: Path, conn: sqlite3.Connection):
    # Archive rows have NULL completed_at — keyset must still paginate them.
    for i in range(5):
        _insert_complete(conn, f"TASK-7{i:02d}", completed_at=None, status="archive")
    seen: list[str] = []
    cursor = None
    for _ in range(10):
        env = _parse(
            mcp_tools.cos_task_board(
                conn, status_filter=["archive"], page_size=2, cursor=cursor, apply_budget=False
            )
        )
        seen.extend(c["id"] for c in env["data"]["cards"])
        cursor = env["data"]["columns"]["archive"]["next_cursor"]
        if not cursor:
            break
    assert len(set(seen)) == 5


def test_board_default_excludes_complete(project: Path, conn: sqlite3.Connection):
    _insert_complete(conn, "TASK-960", completed_at=1)
    env = _parse(mcp_tools.cos_task_board(conn))  # no include_archive
    statuses = {c["status"] for c in env["data"]["cards"]}
    assert "complete" not in statuses
    assert "complete" not in env["data"]["columns"]


def test_board_include_archive_returns_active_and_paged(project: Path, conn: sqlite3.Connection):
    mcp_tools.cos_task_create(conn, title="active", swimlane="core", kind="feature")
    _insert_complete(conn, "TASK-950", completed_at=1)
    env = _parse(mcp_tools.cos_task_board(conn, include_archive=True, apply_budget=False))
    statuses = {c["status"] for c in env["data"]["cards"]}
    assert "icebox" in statuses  # active column in full
    assert "complete" in statuses  # paged column first page
    assert env["data"]["columns"]["complete"]["total_count"] == 1


def test_board_include_archive_on_plain_tuple_connection(
    project: Path, conn: sqlite3.Connection, tmp_path: Path
):
    """Regression: the web _db_conn() opens SQLite WITHOUT row_factory=sqlite3.Row,
    so paged rows are plain tuples. _keyset_column_page must build next_cursor via
    positional access — last["completed_at"] raised "tuple indices must be integers"
    and broke the board tab's include_archive request. init_db's Row factory hid the
    bug from every other keyset test, so this one uses a bare connection on purpose.
    """
    for i in range(7):  # > page_size → has_more=True → the next_cursor line runs
        _insert_complete(conn, f"TASK-6{i:02d}", completed_at=2000 + i)

    # A bare connection, NO row_factory — exactly like web/routes/board.py::_db_conn().
    plain = sqlite3.connect(str(tmp_path / "coding-os.db"))
    try:
        env = _parse(
            mcp_tools.cos_task_board(plain, include_archive=True, page_size=3, apply_budget=False)
        )
    finally:
        plain.close()

    assert env["ok"] is True  # pre-fix: @safe_tool caught the TypeError → ok=False
    assert env["data"]["columns"]["complete"]["next_cursor"]  # positional cursor built


def test_commits_referencing_batch_attributes_per_task(tmp_path: Path):
    import subprocess

    root = tmp_path / "repo"
    root.mkdir()

    def git(*args):
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)

    git("init")
    git("config", "user.email", "t@t.t")
    git("config", "user.name", "t")
    (root / "a.txt").write_text("1")
    git("add", "a.txt")
    git("commit", "-m", "feat: work on TASK-100")
    (root / "b.txt").write_text("2")
    git("add", "b.txt")
    git("commit", "-m", "fix: TASK-100 followup and TASK-200")
    (root / "c.txt").write_text("3")
    git("add", "c.txt")
    git("commit", "-m", "chore: TASK-1000 only")

    counts = mcp_tools._commits_referencing_batch(
        ["TASK-100", "TASK-200", "TASK-300", "TASK-1000"], root
    )
    assert counts["TASK-100"] == 2  # boundary: NOT bumped by TASK-1000
    assert counts["TASK-200"] == 1
    assert counts["TASK-300"] == 0
    assert counts["TASK-1000"] == 1


def test_commits_referencing_batch_no_git_fails_safe(tmp_path: Path):
    # No git repo → every id maps to None so callers treat as "has evidence".
    counts = mcp_tools._commits_referencing_batch(["TASK-1", "TASK-2"], tmp_path)
    assert counts == {"TASK-1": None, "TASK-2": None}
