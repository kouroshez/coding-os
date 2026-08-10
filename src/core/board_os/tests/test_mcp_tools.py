"""Tests for core.board_os.mcp_tools — L.3 MCP surface."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import yaml

from core.board_os import mcp_tools

from .conftest import _parse


def test_create_task_happy_path(project: Path, conn: sqlite3.Connection):
    env = _parse(
        mcp_tools.cos_task_create(
            conn,
            title="Wire L.3 tools",
            swimlane="core",
            kind="feature",
            priority="P1",
            appetite="2h",
            labels=["mcp"],
            outcome="MCP tools importable and registered.",
        )
    )
    assert env["ok"] is True
    data = env["data"]
    assert data["task_id"] == "TASK-001"
    assert data["swimlane"] == "core"
    assert data["kind"] == "feature"

    md = project / data["file_path"]
    assert md.exists()
    content = md.read_text(encoding="utf-8")
    assert "id: TASK-001" in content
    assert 'title: "Wire L.3 tools"' in content
    assert "Wire L.3 tools" in content
    assert "kind: feature" in content


def test_create_task_title_with_double_quote_stays_valid_yaml(
    project: Path, conn: sqlite3.Connection
):
    # Regression: a title containing a double-quote must render
    # valid YAML so the task stays editable through the semantic ops.
    env = _parse(
        mcp_tools.cos_task_create(
            conn,
            title='Fix "ready" gate',
            swimlane="core",
            kind="bug",
            outcome="Quoted title round-trips through YAML.",
        )
    )
    assert env["ok"] is True
    task_id = env["data"]["task_id"]
    content = (project / env["data"]["file_path"]).read_text(encoding="utf-8")

    parsed = yaml.safe_load(content.split("---", 2)[1])
    assert parsed["title"] == 'Fix "ready" gate'

    # Editable via the semantic op — would fail with 'not in lean frontmatter
    # format' if the YAML were broken by an unescaped inner quote.
    edited = _parse(mcp_tools.cos_task_edit(conn, task_id=task_id, priority="P0"))
    assert edited["ok"] is True


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


def test_create_attributes_human_when_session_is_human(project, conn):
    # The web manual-create path passes agent_session='human' so a
    # human-made task is attributed to the human, not the active agent panel.
    created = _parse(
        mcp_tools.cos_task_create(
            conn,
            title="Made by a human",
            swimlane="core",
            kind="feature",
            outcome="A human-made task.",
            agent_session="human",
        )
    )
    hist = _parse(mcp_tools.cos_task_history(conn, task_id=created["data"]["task_id"]))
    assert hist["ok"] is True
    assert hist["data"]["summary"]["created_by"] == "human"


def test_create_attributes_agent_when_session_is_agent(project, conn):
    created = _parse(
        mcp_tools.cos_task_create(
            conn,
            title="Made by an agent",
            swimlane="core",
            kind="feature",
            outcome="An agent-made task.",
            agent_session="ses-claude-20260605-185000-zzzz",
        )
    )
    hist = _parse(mcp_tools.cos_task_history(conn, task_id=created["data"]["task_id"]))
    assert hist["data"]["summary"]["created_by"] == "claude"


# ---------- cos_task_show ----------


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


def test_create_task_in_progress_stamps_started_and_session(
    project: Path, conn: sqlite3.Connection
):
    """F17 / TASK-029 task-lifecycle: creating a task directly in
    `in_progress` used to leave `started` and `agent_session` null in
    the YAML frontmatter — the DB row had values but the file did
    not. After fix both layers agree on creation."""
    env = _parse(
        mcp_tools.cos_task_create(
            conn,
            title="In-progress at creation",
            swimlane="core",
            kind="feature",
            status="in_progress",
            outcome="Stamp started + agent_session when a task is created directly in progress.",
            acceptance=(
                "- **Given** a task created with status=in_progress\n"
                "- **When** the create completes\n"
                "- **Then** started and agent_session are non-null in the file."
            ),
            agent_session="ses-test-lifecycle-1",
        )
    )
    assert env["ok"] is True
    md = project / env["data"]["file_path"]
    content = md.read_text(encoding="utf-8")
    assert "started: null" not in content
    assert "agent_session: null" not in content
    assert "ses-test-lifecycle-1" in content


def test_create_task_testing_does_not_stamp_started(project: Path, conn: sqlite3.Connection):
    """F17b: only `in_progress` stamps `started` at create-time to
    match `workflow.transition` semantics. Tasks created directly in
    `testing` / `emergency` are unusual and should reach those states
    via transition; keep create-path conservative so the two layers
    do not diverge."""
    env = _parse(
        mcp_tools.cos_task_create(
            conn,
            title="Created in testing",
            swimlane="core",
            kind="feature",
            status="testing",
            agent_session="ses-test-lifecycle-2",
        )
    )
    assert env["ok"] is True
    md = project / env["data"]["file_path"]
    content = md.read_text(encoding="utf-8")
    assert "started: null" in content
    assert "agent_session: null" in content


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


def test_create_task_rejects_unknown_swimlane(project: Path, conn: sqlite3.Connection):
    env = _parse(
        mcp_tools.cos_task_create(
            conn,
            title="x",
            swimlane="nonexistent",
            kind="feature",
        )
    )
    assert env["ok"] is False
    assert env["error"]["category"] == "validation"
    assert "not in config" in env["error"]["message"]


def test_create_task_rejects_bad_kind(project: Path, conn: sqlite3.Connection):
    env = _parse(
        mcp_tools.cos_task_create(
            conn,
            title="x",
            swimlane="core",
            kind="invalid",
        )
    )
    assert env["ok"] is False
    assert env["error"]["category"] == "validation"


def test_create_task_rejects_label_colliding_with_kind(
    project: Path,
    conn: sqlite3.Connection,
):
    env = _parse(
        mcp_tools.cos_task_create(
            conn,
            title="x",
            swimlane="core",
            kind="feature",
            labels=["bug"],
        )
    )
    assert env["ok"] is False
    assert "collides with KIND_ENUM" in env["error"]["message"]


def test_create_task_auto_increments_id(project: Path, conn: sqlite3.Connection):
    e1 = _parse(
        mcp_tools.cos_task_create(
            conn,
            title="first",
            swimlane="core",
            kind="chore",
        )
    )
    e2 = _parse(
        mcp_tools.cos_task_create(
            conn,
            title="second",
            swimlane="core",
            kind="chore",
        )
    )
    assert e1["data"]["task_id"] == "TASK-001"
    assert e2["data"]["task_id"] == "TASK-002"


# ---------- cos_task_board ----------


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


# ---------- cos_task_board keyset pagination (TASK-223) ----------


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
