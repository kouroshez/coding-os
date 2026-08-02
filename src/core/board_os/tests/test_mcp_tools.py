"""Tests for core.board_os.mcp_tools — L.3 MCP surface."""

from __future__ import annotations

import importlib.util
import json
import os
import re
import sqlite3
import time
from pathlib import Path

import pytest
import yaml


def _load_db_module():
    spec = importlib.util.spec_from_file_location(
        "_db_under_test",
        Path(__file__).resolve().parents[2] / "thinking_os" / "database.py",
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


db = _load_db_module()

from core.board_os import mcp_tools


@pytest.fixture
def project(tmp_path: Path, monkeypatch) -> Path:
    """Set up a minimal project with scrumban-config.yaml."""
    (tmp_path / ".coding-os").mkdir()
    (tmp_path / ".coding-os" / "scrumban-config.yaml").write_text(
        yaml.safe_dump(
            {
                "swimlanes": [
                    {"id": "core", "label": "Core", "color": "#3b82f6"},
                    {"id": "docs", "label": "Docs", "color": "#a855f7"},
                ],
                "wip_limits": {"in_progress": 2, "testing": 3, "emergency": 2},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "docs" / "tasks").mkdir(parents=True)
    monkeypatch.setenv("COS_PROJECT_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    return db.init_db(tmp_path / "coding-os.db")


def _parse(envelope: str) -> dict:
    return json.loads(envelope)


# ---------- cos_task_create ----------


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


# ---------- cos_task_move ----------


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


# ---------- _close_learning_loop_safe (MCP completion path) ----------


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


# ---------- cos_task_pick ----------


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


# ---------- cos_task_wip_check ----------


def test_wip_check(project: Path, conn: sqlite3.Connection):
    env = _parse(mcp_tools.cos_task_wip_check(conn))
    assert env["ok"] is True
    assert env["data"]["counts"]["in_progress"] == 0
    assert env["data"]["caps"]["in_progress"] == 2
    assert env["data"]["over_cap"] is False


# ---------- cos_work_log_append ----------


def test_work_log_append(project: Path, conn: sqlite3.Connection):
    _parse(
        mcp_tools.cos_task_create(
            conn,
            title="log me",
            swimlane="core",
            kind="feature",
        )
    )
    env = _parse(
        mcp_tools.cos_work_log_append(
            conn,
            task_id="TASK-001",
            summary="did a thing",
            agent_session="ses-claude-xyz",
        )
    )
    assert env["ok"] is True

    md_path = project / "docs" / "tasks" / "TASK-001-log-me.md"
    content = md_path.read_text(encoding="utf-8")
    assert "did a thing" in content
    assert "## Work Log" in content


def test_work_log_append_ignores_prose_mention_of_heading(
    project: Path,
    conn: sqlite3.Connection,
):
    """A `## Work Log` mention inside prose must not capture the append —
    the entry lands under the real heading, not above it."""
    import re as _re

    _parse(
        mcp_tools.cos_task_create(
            conn,
            title="prose mention",
            swimlane="core",
            kind="feature",
        )
    )
    _parse(
        mcp_tools.cos_task_edit(
            conn,
            task_id="TASK-001",
            body=(
                "# TASK-001: prose mention\n\n"
                "**Outcome (one sentence):** test the heading anchor.\n\n"
                "## Acceptance (G/W/T)\n"
                "- **Given** a task whose `## Work Log` is appended, "
                "**When** it runs, **Then** ok.\n\n"
                "## Work Log\n"
            ),
        )
    )
    _parse(
        mcp_tools.cos_work_log_append(
            conn,
            task_id="TASK-001",
            summary="under the heading please",
        )
    )
    md_path = project / "docs" / "tasks" / "TASK-001-prose-mention.md"
    content = md_path.read_text(encoding="utf-8")
    head = _re.search(r"(?m)^## Work Log[ \t]*$", content)
    assert head is not None, content
    # The entry must sit AFTER the real heading, never in the prose above it.
    assert "under the heading please" in content[head.end() :]
    assert "under the heading please" not in content[: head.start()]


def test_work_log_truncates_long_summary(
    project: Path,
    conn: sqlite3.Connection,
):
    mcp_tools.cos_task_create(
        conn,
        title="trunc",
        swimlane="core",
        kind="chore",
    )
    long_summary = "x" * 500
    env = _parse(
        mcp_tools.cos_work_log_append(
            conn,
            task_id="TASK-001",
            summary=long_summary,
        )
    )
    assert env["ok"] is True
    # Line should be ≤ 120 chars of summary
    line = env["data"]["line_appended"]
    # Format: "- YYYY-MM-DD [agent]: xxx"
    summary_part = line.split(": ", 1)[1]
    assert len(summary_part) <= 120


def test_work_log_truncation_marks_loss_with_ellipsis(
    project: Path,
    conn: sqlite3.Connection,
):
    mcp_tools.cos_task_create(conn, title="ellipsis", swimlane="core", kind="chore")
    long_summary = "word " * 40  # 199 chars after strip, many word boundaries
    env = _parse(
        mcp_tools.cos_work_log_append(
            conn,
            task_id="TASK-001",
            summary=long_summary,
        )
    )
    summary_part = env["data"]["line_appended"].split(": ", 1)[1]
    assert len(summary_part) <= 120
    # The loss is marked, not silent.
    assert summary_part.endswith("…")
    # The cut fell on a word boundary, not mid-word.
    kept = summary_part[:-1].rstrip()
    assert long_summary.strip().startswith(kept)
    assert long_summary.strip()[len(kept)] == " "


def test_work_log_uses_readable_agent_label_from_session(
    project: Path,
    conn: sqlite3.Connection,
):
    _parse(
        mcp_tools.cos_task_create(
            conn,
            title="label",
            swimlane="core",
            kind="feature",
        )
    )
    env = _parse(
        mcp_tools.cos_work_log_append(
            conn,
            task_id="TASK-001",
            summary="done",
            agent_session="ses-codex-20260423-abc",
        )
    )
    assert env["ok"] is True
    assert "[codex]" in env["data"]["line_appended"]


# ---------- cos_task_daily ----------


def test_daily_shape(project: Path, conn: sqlite3.Connection):
    mcp_tools.cos_task_create(
        conn,
        title="a",
        swimlane="core",
        kind="chore",
    )
    mcp_tools.cos_task_move(conn, task_id="TASK-001", to="ready", force=True)
    mcp_tools.cos_task_move(
        conn,
        task_id="TASK-001",
        to="in_progress",
        force=True,
    )

    env = _parse(mcp_tools.cos_task_daily(conn))
    assert env["ok"] is True
    d = env["data"]
    assert isinstance(d["yesterday"], list)
    assert isinstance(d["in_progress"], list)
    assert len(d["in_progress"]) == 1
    assert d["wip"]["counts"]["in_progress"] == 1


# ---------- cos_task_retro ----------


def test_retro_shape(project: Path, conn: sqlite3.Connection):
    env = _parse(mcp_tools.cos_task_retro(conn, since="7d"))
    assert env["ok"] is True
    assert "completed_count" in env["data"]
    assert "swimlane_throughput" in env["data"]


def _insert_hook_block(conn, hook: str, session: str, days_ago: float) -> None:
    import time as _time
    from datetime import datetime as _dt

    at = _dt.utcfromtimestamp(_time.time() - days_ago * 86400).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn.execute(
        "INSERT INTO log_events (ts, lvl, scope, msg, kv, session_id, fingerprint, created_at) "
        "VALUES (?, 'ERROR', ?, 'blocked', ?, ?, 'test-fp', ?)",
        (at, f"hook.{hook}", '{"action": "block", "session": "' + session + '"}', session, at),
    )


def test_retro_reports_hook_block_trend(project: Path, conn: sqlite3.Connection):
    """Blocks/session per top hook + trend vs the prior period, from log_events."""
    for _ in range(2):
        _insert_hook_block(conn, "enforce-skill", "ses-a", days_ago=1)
    _insert_hook_block(conn, "thinking_os-gate", "ses-b", days_ago=2)
    for _ in range(4):
        _insert_hook_block(conn, "enforce-skill", "ses-old", days_ago=10)
    conn.commit()
    data = _parse(mcp_tools.cos_task_retro(conn, since="7d"))["data"]
    trend = data["hook_block_trend"]
    assert trend["blocks"] == 3
    assert trend["sessions"] == 2
    assert trend["blocks_per_session"] == 1.5
    assert trend["previous_blocks_per_session"] == 4.0
    assert trend["trend"] == "improving"
    assert trend["top_hooks"][0] == {"hook": "enforce-skill", "blocks": 2}


def test_retro_omits_hook_block_trend_when_no_events(project: Path, conn: sqlite3.Connection):
    data = _parse(mcp_tools.cos_task_retro(conn, since="7d"))["data"]
    assert "hook_block_trend" not in data


# ---------- concurrent id allocation ----------


def test_concurrent_create_yields_unique_ids(project: Path, conn: sqlite3.Connection):
    """N threads each open their own connection to the SAME db file and
    create a task at once — every allocated TASK-NNN must be unique
    (atomic INSERT…SELECT reservation, not read-then-write)."""
    import threading

    db_path = project / "coding-os.db"
    results: list[str] = []
    errors: list[dict] = []
    lock = threading.Lock()
    barrier = threading.Barrier(12)

    def worker(i: int) -> None:
        c = sqlite3.connect(str(db_path), timeout=5)
        try:
            barrier.wait()  # maximize collision pressure
            env = json.loads(
                mcp_tools.cos_task_create(
                    c,
                    title=f"concurrent {i}",
                    swimlane="core",
                    kind="chore",
                    outcome="concurrent allocation regression guard outcome.",
                )
            )
            with lock:
                (results if env["ok"] else errors).append(
                    env["data"]["task_id"] if env["ok"] else env
                )
        finally:
            c.close()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, errors
    assert len(results) == 12, results
    assert len(set(results)) == 12, f"duplicate ids allocated: {sorted(results)}"


def test_pooled_conn_threads_create_safely(project: Path, conn: sqlite3.Connection):
    """N threads each obtain a per-thread pooled connection (the machinery the
    MCP server wrappers use instead of sharing one module-level connection
    across the FastMCP threadpool) and create concurrently — every create
    succeeds with a unique id and no cross-thread interleaving error."""
    import threading

    from database import get_pooled_conn

    db_path = project / "coding-os.db"
    results: list[str] = []
    errors: list[dict] = []
    lock = threading.Lock()
    barrier = threading.Barrier(8)

    def worker(i: int) -> None:
        pooled = get_pooled_conn(db_path)
        barrier.wait()
        env = json.loads(
            mcp_tools.cos_task_create(
                pooled,
                title=f"pooled concurrent {i}",
                swimlane="core",
                kind="chore",
                outcome="pooled per-thread connection regression guard outcome.",
            )
        )
        with lock:
            (results if env["ok"] else errors).append(env["data"]["task_id"] if env["ok"] else env)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, errors
    assert len(set(results)) == 8, f"expected 8 unique ids: {sorted(results)}"


# ---------- cos_task_reclaim (zombie recovery, TASK-089) ----------


def test_reclaim_moves_idle_in_progress_to_icebox_ready(project: Path, conn: sqlite3.Connection):
    import time as _t

    env = _parse(
        mcp_tools.cos_task_create(
            conn,
            title="zombie",
            swimlane="core",
            kind="chore",
            outcome="zombie reclaim regression guard outcome.",
            ready=True,
        )
    )
    tid = env["data"]["task_id"]
    assert _parse(
        mcp_tools.cos_task_move(conn, task_id=tid, to="in_progress", agent_session="ses-dead")
    )["ok"]

    old = int(_t.time()) - 48 * 3600
    conn.execute("UPDATE tasks SET started_at = ? WHERE task_id = ?", (old, tid))
    conn.execute("UPDATE task_status_history SET transitioned_at = ? WHERE task_id = ?", (old, tid))
    conn.commit()

    rec = _parse(mcp_tools.cos_task_reclaim(conn))
    assert rec["ok"], rec
    assert tid in [r["task_id"] for r in rec["data"]["reclaimed"]]

    row = conn.execute("SELECT status, labels_json FROM tasks WHERE task_id = ?", (tid,)).fetchone()
    assert row[0] == "icebox"
    assert "ready" in (row[1] or "")


def test_reclaim_skips_fresh_in_progress(project: Path, conn: sqlite3.Connection):
    env = _parse(
        mcp_tools.cos_task_create(
            conn,
            title="fresh",
            swimlane="core",
            kind="chore",
            outcome="fresh task must not be reclaimed outcome.",
            ready=True,
        )
    )
    tid = env["data"]["task_id"]
    assert _parse(
        mcp_tools.cos_task_move(conn, task_id=tid, to="in_progress", agent_session="ses-x")
    )["ok"]

    rec = _parse(mcp_tools.cos_task_reclaim(conn))
    assert rec["ok"], rec
    assert tid not in [r["task_id"] for r in rec["data"]["reclaimed"]]
    row = conn.execute("SELECT status FROM tasks WHERE task_id = ?", (tid,)).fetchone()
    assert row[0] == "in_progress"


def test_task_history_returns_create_and_status_events(project: Path, conn: sqlite3.Connection):
    """cos_task_history surfaces the creation event + status transitions,
    each actor-attributed."""
    created = _parse(
        mcp_tools.cos_task_create(
            conn,
            title="History sample",
            swimlane="core",
            kind="chore",
            outcome="Bump dep X to patched version Y for the security advisory.",
            ready=True,
            agent_session="ses-claude-hist",
        )
    )
    task_id = created["data"]["task_id"]
    assert _parse(
        mcp_tools.cos_task_move(
            conn, task_id=task_id, to="in_progress", agent_session="ses-claude-hist"
        )
    )["ok"]

    env = _parse(mcp_tools.cos_task_history(conn, task_id=task_id, include_commits=False))
    assert env["ok"] is True
    types = [e["type"] for e in env["data"]["events"]]
    assert "created" in types
    assert "status" in types
    created_evt = next(e for e in env["data"]["events"] if e["type"] == "created")
    assert created_evt["actor"]["type"] == "agent"
    assert created_evt["actor"]["label"] == "claude"
    assert env["data"]["summary"]["created_by"] == "claude"


def test_task_history_not_found(project: Path, conn: sqlite3.Connection):
    env = _parse(mcp_tools.cos_task_history(conn, task_id="TASK-999", include_commits=False))
    assert env["ok"] is False
    assert env["error"]["category"] == "not_found"


def test_task_history_links_worklog_commits_without_id_in_message(
    project: Path, conn: sqlite3.Connection
):
    """History links a code commit referenced in the Work Log even though its
    message has NO task id and it never touched the task md file (TASK-264) —
    so commits and tasks link without a task-number-in-commit convention."""
    import subprocess

    def _git(*args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(project), *args], capture_output=True, text=True, check=True
        ).stdout.strip()

    _git("init", "-q")
    _git("config", "user.email", "t@example.com")
    _git("config", "user.name", "tester")
    (project / "code.txt").write_text("x", encoding="utf-8")
    _git("add", "code.txt")
    _git("commit", "-q", "-m", "fix something unrelated to any task number")
    full_sha = _git("rev-parse", "HEAD")

    created = _parse(
        mcp_tools.cos_task_create(
            conn,
            title="Linked",
            swimlane="core",
            kind="bug",
            outcome="A long enough outcome to satisfy the bug DoR gate for this linkage test.",
        )
    )
    tid = created["data"]["task_id"]
    mcp_tools.cos_work_log_append(conn, task_id=tid, summary=f"fixed in commit {full_sha[:10]}")

    hist = _parse(mcp_tools.cos_task_history(conn, task_id=tid, include_commits=True))
    commit_shas = [e["sha"] for e in hist["data"]["events"] if e.get("type") == "commit"]
    assert any(full_sha.startswith(s) for s in commit_shas), (
        "a work-log SHA must link the commit in History without a task id in its message"
    )


def test_task_edit_updates_field_and_records_history(project: Path, conn: sqlite3.Connection):
    """A field edit rewrites the file and lands an actor-attributed edit-history row."""
    created = _parse(
        mcp_tools.cos_task_create(
            conn,
            title="Edit me",
            swimlane="core",
            kind="chore",
            outcome="Initial outcome long enough for the chore DoR gate.",
        )
    )
    tid = created["data"]["task_id"]
    env = _parse(
        mcp_tools.cos_task_edit(
            conn, task_id=tid, priority="P0", actor_type="human", actor_id="kourosh", source="web"
        )
    )
    assert env["ok"] is True
    assert "priority" in env["data"]["changed"]
    content = (project / created["data"]["file_path"]).read_text(encoding="utf-8")
    assert "priority: P0" in content

    hist = _parse(mcp_tools.cos_task_history(conn, task_id=tid, include_commits=False))
    edits = [e for e in hist["data"]["events"] if e["type"] == "edit"]
    assert any(e["field"] == "priority" and e["actor"]["id"] == "kourosh" for e in edits)


def test_task_edit_noop_when_unchanged(project: Path, conn: sqlite3.Connection):
    created = _parse(mcp_tools.cos_task_create(conn, title="Same", swimlane="core", kind="chore"))
    tid = created["data"]["task_id"]
    env = _parse(mcp_tools.cos_task_edit(conn, task_id=tid, title="Same"))
    assert env["ok"] is True
    assert env["data"]["changed"] == []


def test_task_edit_rejects_bad_swimlane(project: Path, conn: sqlite3.Connection):
    created = _parse(mcp_tools.cos_task_create(conn, title="x", swimlane="core", kind="chore"))
    tid = created["data"]["task_id"]
    env = _parse(mcp_tools.cos_task_edit(conn, task_id=tid, swimlane="nope"))
    assert env["ok"] is False
    assert env["error"]["category"] == "validation"


def test_task_edit_body_rewrites_file(project: Path, conn: sqlite3.Connection):
    """Editing the body replaces it and preserves frontmatter."""
    created = _parse(
        mcp_tools.cos_task_create(conn, title="Body edit", swimlane="core", kind="chore")
    )
    tid = created["data"]["task_id"]
    new_body = f"# {tid}: Body edit\n\n**Outcome (one sentence):** Rewritten outcome via edit.\n\n## Work Log\n"
    env = _parse(mcp_tools.cos_task_edit(conn, task_id=tid, body=new_body))
    assert env["ok"] is True
    assert "body" in env["data"]["changed"]
    content = (project / created["data"]["file_path"]).read_text(encoding="utf-8")
    assert "Rewritten outcome via edit." in content
    assert content.startswith("---")  # frontmatter preserved


def test_start_auto_reclaims_idle_zombie(project: Path, conn: sqlite3.Connection):
    """Pulling a task into in_progress auto-frees an idle zombie of a dead
    session — the board self-heals without a manual cos task-reclaim."""
    import time as _t

    z = _parse(
        mcp_tools.cos_task_create(
            conn,
            title="zombie auto",
            swimlane="core",
            kind="chore",
            outcome="zombie auto-reclaimed on next start outcome.",
            ready=True,
        )
    )
    ztid = z["data"]["task_id"]
    assert _parse(
        mcp_tools.cos_task_move(conn, task_id=ztid, to="in_progress", agent_session="ses-dead-auto")
    )["ok"]
    old = int(_t.time()) - 48 * 3600
    conn.execute("UPDATE tasks SET started_at = ? WHERE task_id = ?", (old, ztid))
    conn.execute(
        "UPDATE task_status_history SET transitioned_at = ? WHERE task_id = ?", (old, ztid)
    )
    conn.commit()

    live = _parse(
        mcp_tools.cos_task_create(
            conn,
            title="live starter",
            swimlane="core",
            kind="chore",
            outcome="live task whose start triggers auto-reclaim outcome.",
            ready=True,
        )
    )
    ltid = live["data"]["task_id"]
    started = _parse(
        mcp_tools.cos_task_move(conn, task_id=ltid, to="in_progress", agent_session="ses-live-auto")
    )
    assert started["ok"], started

    zrow = conn.execute("SELECT status FROM tasks WHERE task_id = ?", (ztid,)).fetchone()
    assert zrow[0] == "icebox", "idle zombie should be auto-reclaimed on the next start"


def test_task_edit_body_preserves_canonical_h1(project: Path, conn: sqlite3.Connection):
    """The web panel strips the `# TASK-NNN: title` H1 for display and sends an
    H1-less body; cos_task_edit must restore the canonical H1 so a panel edit
    never corrupts the file structure."""
    created = _parse(
        mcp_tools.cos_task_create(conn, title="H1 task", swimlane="core", kind="chore")
    )
    tid = created["data"]["task_id"]
    env = _parse(
        mcp_tools.cos_task_edit(
            conn,
            task_id=tid,
            body="**Outcome (one sentence):** edited via panel.\n\n## Work Log\n",
        )
    )
    assert env["ok"] is True
    content = (project / created["data"]["file_path"]).read_text(encoding="utf-8")
    assert f"# {tid}: H1 task" in content, "canonical H1 must survive a panel body edit"


def test_task_edit_title_updates_h1(project: Path, conn: sqlite3.Connection):
    """Editing the title must propagate to the body H1 — no stale title left."""
    created = _parse(
        mcp_tools.cos_task_create(conn, title="Old title", swimlane="core", kind="chore")
    )
    tid = created["data"]["task_id"]
    env = _parse(mcp_tools.cos_task_edit(conn, task_id=tid, title="New title"))
    assert env["ok"] is True
    content = (project / created["data"]["file_path"]).read_text(encoding="utf-8")
    assert f"# {tid}: New title" in content
    assert "Old title" not in content, "stale title must not linger in the H1"


# ---------- F1: board time dimension (status_dwell + stale) — TASK-210 RC5 ----------


def _backdate_task(conn: sqlite3.Connection, task_id: str, status: str, seconds_ago: int) -> None:
    old = int(time.time()) - seconds_ago
    conn.execute("UPDATE tasks SET status=?, started_at=? WHERE task_id=?", (status, old, task_id))
    conn.execute("UPDATE task_status_history SET transitioned_at=? WHERE task_id=?", (old, task_id))
    conn.commit()


def test_task_card_exposes_dwell_and_timestamps(project: Path, conn: sqlite3.Connection):
    """RC5: _task_card surfaces the time dimension it previously dropped."""
    mcp_tools.cos_task_create(
        conn,
        title="Dwell card",
        swimlane="core",
        kind="chore",
        status="in_progress",
        outcome="Card carries a dwell signal for every board surface.",
        acceptance="**Given** a card\n**When** rendered\n**Then** dwell is present",
        read_first=["docs/governance/task-lifecycle.md"],
    )
    env = _parse(mcp_tools.cos_task_board(conn))
    card = env["data"]["cards"][0]
    for key in (
        "started_at",
        "completed_at",
        "last_transition_at",
        "status_dwell_seconds",
        "status_dwell_human",
        "stale",
    ):
        assert key in card, f"board card missing {key}"
    # A just-started in_progress card is not stale under the default 24h SLA.
    assert card["stale"] is False


def test_board_flags_stale_testing_card(project: Path, conn: sqlite3.Connection):
    """RC3: a testing card past its SLA is flagged stale on the board (read-only)."""
    mcp_tools.cos_task_create(
        conn, title="Old testing", swimlane="core", kind="bug", status="icebox"
    )
    _backdate_task(conn, "TASK-001", "testing", 8 * 3600)  # > testing_sla_hours (6h)
    env = _parse(mcp_tools.cos_task_board(conn, status_filter=["testing"]))
    card = next(c for c in env["data"]["cards"] if c["id"] == "TASK-001")
    assert card["status"] == "testing"
    assert card["stale"] is True
    assert card["status_dwell_seconds"] >= 6 * 3600


def test_board_flags_stale_blocked_card(project: Path, conn: sqlite3.Connection):
    """TASK-663: a card parked in blocked past blocked_sla_hours is flagged stale
    (observability only — it stays blocked, never auto-escalated to emergency)."""
    mcp_tools.cos_task_create(
        conn, title="Old blocked", swimlane="core", kind="bug", status="icebox"
    )
    _backdate_task(conn, "TASK-001", "blocked", 80 * 3600)  # > blocked_sla_hours (72h default)
    env = _parse(mcp_tools.cos_task_board(conn, status_filter=["blocked"]))
    card = next(c for c in env["data"]["cards"] if c["id"] == "TASK-001")
    assert card["status"] == "blocked"  # never moved to emergency
    assert card["stale"] is True
    assert "blocked" in (card["stale_reason"] or "")


def test_board_fresh_blocked_card_not_stale(project: Path, conn: sqlite3.Connection):
    """TASK-663: a blocked card under the SLA is not stale."""
    mcp_tools.cos_task_create(
        conn, title="Fresh blocked", swimlane="core", kind="bug", status="icebox"
    )
    _backdate_task(conn, "TASK-001", "blocked", 10 * 3600)  # < 72h
    env = _parse(mcp_tools.cos_task_board(conn, status_filter=["blocked"]))
    card = next(c for c in env["data"]["cards"] if c["id"] == "TASK-001")
    assert card["stale"] is False
    assert card["stale_reason"] is None


def test_sla_threshold_blocked_is_config_driven():
    """TASK-663: the blocked threshold comes from config (no hardcode); 0 disables."""

    class _Policy:
        in_progress_sla_hours = 24
        testing_sla_hours = 6
        icebox_stale_days = 30
        blocked_sla_hours = 5

    class _Config:
        workflow_policy = _Policy()

    assert mcp_tools._sla_threshold_seconds("blocked", _Config()) == 5 * 3600
    _Policy.blocked_sla_hours = 0
    assert mcp_tools._sla_threshold_seconds("blocked", _Config()) is None


def test_daily_reports_testing_and_icebox_summary(project: Path, conn: sqlite3.Connection):
    """RC3/RC6: daily surfaces testing cards and icebox depth/staleness."""
    # Fresh testing card — recent activity so reclaim leaves it; daily must REPORT it.
    mcp_tools.cos_task_create(
        conn, title="Active testing", swimlane="core", kind="bug", status="icebox"
    )
    conn.execute(
        "UPDATE tasks SET status='testing', started_at=? WHERE task_id='TASK-001'",
        (int(time.time()),),
    )
    conn.commit()
    # Stale icebox idea (icebox is never reclaimed, only surfaced).
    mcp_tools.cos_task_create(
        conn, title="Old idea", swimlane="core", kind="chore", status="icebox"
    )
    _backdate_task(conn, "TASK-002", "icebox", 40 * 86400)  # > icebox_stale_days (30d)
    env = _parse(mcp_tools.cos_task_daily(conn))
    data = env["data"]
    assert any(c["id"] == "TASK-001" for c in data["testing"]), "daily must report testing"
    assert data["icebox"]["total"] >= 1
    assert "TASK-002" in data["icebox"]["stale_ids"]


# ---------- F2a: reclaim widening — TASK-210 RC3/RC4 ----------


def test_reclaim_returns_stale_testing_to_in_progress(project, conn, monkeypatch):
    """RC3: a stale testing zombie is reclaimed back to in_progress (not icebox)."""
    monkeypatch.setattr(mcp_tools, "_commits_referencing", lambda *a, **k: 0)  # git-verified zero
    monkeypatch.setattr(
        mcp_tools, "_commits_referencing_batch", lambda ids, *a, **k: {t: 0 for t in ids}
    )
    mcp_tools.cos_task_create(
        conn, title="Testing zombie", swimlane="core", kind="bug", status="icebox"
    )
    _backdate_task(conn, "TASK-001", "testing", 8 * 3600)  # > testing_reclaim_idle_hours (6h)
    env = _parse(mcp_tools.cos_task_reclaim(conn))
    assert env["ok"] is True
    entry = next(r for r in env["data"]["reclaimed"] if r["task_id"] == "TASK-001")
    assert entry["from_status"] == "testing"
    assert entry["to_status"] == "in_progress"
    assert (
        conn.execute("SELECT status FROM tasks WHERE task_id='TASK-001'").fetchone()[0]
        == "in_progress"
    )


def test_reclaim_in_progress_to_icebox_ready(project: Path, conn: sqlite3.Connection):
    """An in_progress zombie still drops to icebox and regains the ready label."""
    mcp_tools.cos_task_create(conn, title="IP zombie", swimlane="core", kind="bug", status="icebox")
    _backdate_task(conn, "TASK-001", "in_progress", 30 * 3600)  # > 24h
    env = _parse(mcp_tools.cos_task_reclaim(conn))
    entry = next(r for r in env["data"]["reclaimed"] if r["task_id"] == "TASK-001")
    assert entry["to_status"] == "icebox"
    row = conn.execute("SELECT status, labels_json FROM tasks WHERE task_id='TASK-001'").fetchone()
    assert row[0] == "icebox"
    assert "ready" in (row[1] or "")


def test_reclaim_per_status_testing_sooner_than_in_progress(project, conn, monkeypatch):
    """A 7h testing card reclaims (>6h) though it is under the 24h in_progress floor."""
    monkeypatch.setattr(mcp_tools, "_commits_referencing", lambda *a, **k: 0)  # git-verified zero
    monkeypatch.setattr(
        mcp_tools, "_commits_referencing_batch", lambda ids, *a, **k: {t: 0 for t in ids}
    )
    mcp_tools.cos_task_create(
        conn, title="7h testing", swimlane="core", kind="bug", status="icebox"
    )
    _backdate_task(conn, "TASK-001", "testing", 7 * 3600)
    env = _parse(mcp_tools.cos_task_reclaim(conn))
    assert any(r["task_id"] == "TASK-001" for r in env["data"]["reclaimed"])


def test_reclaim_skips_fresh_testing(project: Path, conn: sqlite3.Connection):
    """A 1h testing card is left alone (under the 6h testing window)."""
    mcp_tools.cos_task_create(
        conn, title="Fresh testing", swimlane="core", kind="bug", status="icebox"
    )
    _backdate_task(conn, "TASK-001", "testing", 1 * 3600)
    env = _parse(mcp_tools.cos_task_reclaim(conn))
    assert not any(r["task_id"] == "TASK-001" for r in env["data"]["reclaimed"])


# ---------- F5a: terminal archive drain — TASK-210 RC6 ----------


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


# ---------- F5b: icebox auto-archive sweep — TASK-210 RC6 ----------

_SL = [{"id": "core", "label": "Core", "color": "#3b82f6"}]


def test_archive_sweep_off_by_default(project: Path, conn: sqlite3.Connection):
    """Default config (auto_archive_days=0) never deletes backlog."""
    from board_os.config import parse_config

    mcp_tools.cos_task_create(
        conn, title="Old idea", swimlane="core", kind="chore", status="icebox"
    )
    _backdate_task(conn, "TASK-001", "icebox", 100 * 86400)
    archived = mcp_tools._archive_stale_sweep(conn, parse_config({"swimlanes": _SL}))
    assert archived == []
    assert (
        conn.execute("SELECT status FROM tasks WHERE task_id='TASK-001'").fetchone()[0] == "icebox"
    )


def test_archive_sweep_archives_aged_icebox_respecting_keep(
    project: Path, conn: sqlite3.Connection
):
    """Opt-in: aged icebox cards archive, but a keep/parked label exempts."""
    from board_os.config import parse_config

    mcp_tools.cos_task_create(conn, title="Stale", swimlane="core", kind="chore", status="icebox")
    _backdate_task(conn, "TASK-001", "icebox", 40 * 86400)  # > 30d
    mcp_tools.cos_task_create(
        conn, title="Keeper", swimlane="core", kind="chore", status="icebox", labels=["keep"]
    )
    _backdate_task(conn, "TASK-002", "icebox", 40 * 86400)
    cfg = parse_config({"swimlanes": _SL, "workflow_policy": {"icebox_auto_archive_days": 30}})
    archived = mcp_tools._archive_stale_sweep(conn, cfg)
    ids = [a["task_id"] for a in archived]
    assert "TASK-001" in ids and "TASK-002" not in ids
    assert (
        conn.execute("SELECT status FROM tasks WHERE task_id='TASK-001'").fetchone()[0] == "archive"
    )
    assert (
        conn.execute("SELECT status FROM tasks WHERE task_id='TASK-002'").fetchone()[0] == "icebox"
    )


def test_archive_sweep_attributes_to_system_actor(project: Path, conn: sqlite3.Connection):
    """Sweep rows carry a ses-system session — NULL would render as the human operator."""
    from board_os.config import parse_config

    mcp_tools.cos_task_create(conn, title="Stale", swimlane="core", kind="chore", status="icebox")
    _backdate_task(conn, "TASK-001", "icebox", 40 * 86400)
    cfg = parse_config({"swimlanes": _SL, "workflow_policy": {"icebox_auto_archive_days": 30}})
    archived = mcp_tools._archive_stale_sweep(conn, cfg)
    assert [a["task_id"] for a in archived] == ["TASK-001"]
    session = conn.execute(
        "SELECT agent_session FROM task_status_history "
        "WHERE task_id='TASK-001' AND new_status='archive' ORDER BY id DESC LIMIT 1"
    ).fetchone()[0]
    assert session == "ses-system-auto-archive"
    assert mcp_tools._actor_view(session) == {
        "type": "system",
        "id": "ses-system-auto-archive",
        "label": "system",
    }


def test_reclaim_without_session_attributes_to_system_actor(
    project: Path, conn: sqlite3.Connection
):
    """An unattended reclaim (nightly daemon, no session) is system-, not human-attributed."""
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


# ---------- F4: hub/human-actor zombies are reclaimable — TASK-210 MISS-1 ----------


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


# ---------- reconciliation (review-first triage) ----------


def test_reconcile_classifies_likely_complete_via_worklog(project: Path, conn: sqlite3.Connection):
    """A testing zombie with committed/logged work is likely-complete → review & done, not recycle."""
    mcp_tools.cos_task_create(conn, title="Done-ish", swimlane="core", kind="bug", status="icebox")
    _backdate_task(conn, "TASK-001", "testing", 8 * 3600)
    conn.execute(
        "UPDATE tasks SET work_log_last_5=? WHERE task_id='TASK-001'", ('["implemented + tested"]',)
    )
    conn.commit()
    item = next(
        i
        for i in _parse(mcp_tools.cos_task_reconcile(conn))["data"]["stranded"]
        if i["task_id"] == "TASK-001"
    )
    assert item["classification"] == "likely_complete"
    assert "task-done" in item["recommendation"]


def test_reconcile_classifies_likely_abandoned(project, conn, monkeypatch):
    monkeypatch.setattr(mcp_tools, "_commits_referencing", lambda *a, **k: 0)  # git-verified zero
    monkeypatch.setattr(
        mcp_tools, "_commits_referencing_batch", lambda ids, *a, **k: {t: 0 for t in ids}
    )
    mcp_tools.cos_task_create(conn, title="Nothing", swimlane="core", kind="bug", status="icebox")
    _backdate_task(conn, "TASK-001", "in_progress", 30 * 3600)
    conn.execute("UPDATE tasks SET work_log_last_5='[]' WHERE task_id='TASK-001'")
    conn.commit()
    item = next(
        i
        for i in _parse(mcp_tools.cos_task_reconcile(conn))["data"]["stranded"]
        if i["task_id"] == "TASK-001"
    )
    assert item["classification"] == "likely_abandoned"


def test_reconcile_fail_safe_when_git_unverifiable(project, conn, monkeypatch):
    """TASK-217: when commits can't be verified (no git), a testing task is
    likely_complete (never abandoned) and reclaim must NOT recycle it."""
    monkeypatch.setattr(mcp_tools, "_commits_referencing", lambda *a, **k: None)  # can't verify
    monkeypatch.setattr(
        mcp_tools, "_commits_referencing_batch", lambda ids, *a, **k: {t: None for t in ids}
    )
    mcp_tools.cos_task_create(conn, title="No git", swimlane="core", kind="bug", status="icebox")
    _backdate_task(conn, "TASK-001", "testing", 8 * 3600)
    item = next(
        i
        for i in _parse(mcp_tools.cos_task_reconcile(conn))["data"]["stranded"]
        if i["task_id"] == "TASK-001"
    )
    assert item["classification"] == "likely_complete"
    env = _parse(mcp_tools.cos_task_reclaim(conn))
    assert any(s["task_id"] == "TASK-001" for s in env["data"]["skipped_for_review"])
    assert (
        conn.execute("SELECT status FROM tasks WHERE task_id='TASK-001'").fetchone()[0] == "testing"
    )


def test_reconcile_is_read_only(project: Path, conn: sqlite3.Connection):
    """Reconcile is review-first: it must NEVER mutate board state, even called twice."""
    mcp_tools.cos_task_create(conn, title="X", swimlane="core", kind="bug", status="icebox")
    _backdate_task(conn, "TASK-001", "testing", 8 * 3600)
    conn.execute("UPDATE tasks SET work_log_last_5=? WHERE task_id='TASK-001'", ('["w"]',))
    conn.commit()
    cols = "SELECT task_id, status, started_at, labels_json, work_log_last_5 FROM tasks ORDER BY task_id"
    before = conn.execute(cols).fetchall()
    out1 = mcp_tools.cos_task_reconcile(conn)
    out2 = mcp_tools.cos_task_reconcile(conn)
    after = conn.execute(cols).fetchall()
    assert before == after, "reconcile must not mutate any task row"
    assert out1 == out2, "reconcile must be deterministic/idempotent"


def test_reconcile_flags_icebox_zombie_with_completion_claim(project, conn, monkeypatch):
    """A card filed straight into icebox whose log claims implemented+verified is a zombie."""
    monkeypatch.setattr(
        mcp_tools, "_commits_referencing_batch", lambda ids, *a, **k: {t: 1 for t in ids}
    )
    mcp_tools.cos_task_create(
        conn, title="Born zombie", swimlane="core", kind="bug", status="icebox"
    )
    conn.execute(
        "UPDATE tasks SET work_log_last_5=? WHERE task_id='TASK-001'",
        ('["Implemented + verified. Added residue-sweep after global link"]',),
    )
    conn.commit()
    env = _parse(mcp_tools.cos_task_reconcile(conn))
    item = next(i for i in env["data"]["stranded"] if i["task_id"] == "TASK-001")
    assert item["classification"] == "zombie_icebox"
    assert "task-done" in item["recommendation"]
    assert env["data"]["summary"]["zombie_icebox"] == 1


def test_reconcile_ignores_icebox_card_without_completion_claim(project, conn, monkeypatch):
    """A merely-annotated icebox card (scope notes, no completion claim) is not a zombie."""
    monkeypatch.setattr(
        mcp_tools, "_commits_referencing_batch", lambda ids, *a, **k: {t: 1 for t in ids}
    )
    mcp_tools.cos_task_create(
        conn, title="Just parked", swimlane="core", kind="bug", status="icebox"
    )
    conn.execute(
        "UPDATE tasks SET work_log_last_5=? WHERE task_id='TASK-001'",
        ('["Scope correction before pickup: installer already excludes these files"]',),
    )
    conn.commit()
    env = _parse(mcp_tools.cos_task_reconcile(conn))
    assert not any(i["task_id"] == "TASK-001" for i in env["data"]["stranded"])
    assert env["data"]["summary"]["zombie_icebox"] == 0


def test_board_flags_icebox_zombie_stale(project: Path, conn: sqlite3.Connection):
    """cos_task_board marks a zombie icebox card stale with a zombie-specific reason."""
    mcp_tools.cos_task_create(
        conn, title="Zombie flag", swimlane="core", kind="bug", status="icebox"
    )
    conn.execute(
        "UPDATE tasks SET work_log_last_5=? WHERE task_id='TASK-001'",
        ('["committed abc1234f · 2 files"]',),
    )
    conn.commit()
    env = _parse(mcp_tools.cos_task_board(conn, status_filter=["icebox"]))
    card = next(c for c in env["data"]["cards"] if c["id"] == "TASK-001")
    assert card["completion_evidence"] is True
    assert card["stale"] is True
    assert "zombie" in card["stale_reason"]


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


# ---------- cos_task_board envelope budget (TASK-209) ----------


def test_board_caps_to_envelope_budget(project: Path, conn: sqlite3.Connection):
    # TASK-209: a large board must never return an unshrinkable >32KB
    # envelope (the cause of the eye's ERROR flood). The tool caps cards to
    # the budget, signals truncation, and keeps grouped + cards consistent.
    from thinking_os.tools._shared import TOKEN_BUDGET_CHARS

    long = "x" * 160
    for i in range(45):
        mcp_tools.cos_task_create(
            conn,
            title=f"Task {i:02d} {long}",
            swimlane="core",
            kind="feature",
            labels=["alpha", "beta", "gamma"],
            outcome="o",
        )

    env_str = mcp_tools.cos_task_board(conn, limit=50)
    assert len(env_str) <= TOKEN_BUDGET_CHARS  # the whole envelope fits the budget

    data = _parse(env_str)["data"]
    assert data["truncated"] is True
    assert data["total_count"] > data["count"]
    assert not data["meta"].get("envelope_unshrinkable")  # fingerprint gone

    assert len(data["cards"]) == data["count"]  # cards list matches the count (no grouped dupe)


def test_board_small_board_is_not_truncated(project: Path, conn: sqlite3.Connection):
    # A normal small board passes through untouched — the cap is a safety net.
    for i in range(3):
        mcp_tools.cos_task_create(
            conn, title=f"Small {i}", swimlane="core", kind="feature", outcome="o"
        )
    data = _parse(mcp_tools.cos_task_board(conn))["data"]
    assert data["truncated"] is False
    assert data["count"] == data["total_count"] == 3


def test_board_browser_path_skips_envelope_cap(project: Path, conn: sqlite3.Connection):
    # STEP 2 — the user's 186KB ERROR. The browser path passes apply_budget=False,
    # which must skip BOTH the board's own pre-cap AND ok()'s 32KB agent cap, so a
    # large board renders in full with NO envelope_unshrinkable ERROR on the wire.
    # (The agent path on the same board still caps — test_board_caps_to_envelope_budget.)
    from thinking_os.tools._shared import TOKEN_BUDGET_CHARS

    long = "x" * 160
    for i in range(45):
        mcp_tools.cos_task_create(
            conn,
            title=f"Task {i:02d} {long}",
            swimlane="core",
            kind="feature",
            labels=["alpha", "beta", "gamma"],
            outcome="o",
        )

    env_str = mcp_tools.cos_task_board(conn, limit=200, apply_budget=False)
    # Genuinely oversized: under the agent cap this exact board trips the trimmer.
    assert len(env_str) > TOKEN_BUDGET_CHARS
    data = _parse(env_str)["data"]
    # Browser opt-out: full board, no cap, no unshrinkable ERROR fingerprint.
    assert not data["meta"].get("envelope_unshrinkable")
    assert data["meta"]["truncated"] is False
    assert data["truncated"] is False
    assert data["count"] == data["total_count"] == 45  # every card returned


# ---------- cos_task_show output contract (TASK-271) ----------
# Codifies what every caller (hub drawer, agents) relies on, so output quality
# is asserted in CI — not just eyeballed. A future refactor that silently drops
# a field (the TASK-271 regression) now fails here.


def test_task_show_returns_full_field_contract(project: Path, conn: sqlite3.Connection):
    created = _parse(
        mcp_tools.cos_task_create(
            conn,
            title="Contract probe",
            swimlane="core",
            kind="feature",
            epic="hub-redesign",
            labels=["ready", "mcp"],
            outcome="cos_task_show exposes its stored fields.",
        )
    )
    tid = created["data"]["task_id"]

    env = _parse(mcp_tools.cos_task_show(conn, task_id=tid))
    assert env["ok"] is True
    data = env["data"]

    required = {
        "id",
        "title",
        "status",
        "swimlane",
        "kind",
        "priority",
        "appetite",
        "file_path",
        "epic",
        "labels",
        "agent_session",
        "started_at",
        "completed_at",
        "body",
    }
    missing = required - set(data)
    assert not missing, f"cos_task_show dropped fields: {missing}"

    assert data["id"] == tid
    assert data["epic"] == "hub-redesign"
    assert data["labels"] == ["ready", "mcp"]
    assert isinstance(data["labels"], list)
    assert data["meta"]["layer"] == "tasks"


def test_task_show_not_found_returns_fail_envelope(project: Path, conn: sqlite3.Connection):
    env = _parse(mcp_tools.cos_task_show(conn, task_id="TASK-999"))
    assert env["ok"] is False
    assert env["error"]["category"] == "not_found"


# ---------- worklog → timeline events (C3a / TASK-267) ----------


def test_worklog_events_parses_bullets_in_file_order(project: Path, conn: sqlite3.Connection):
    created = _parse(
        mcp_tools.cos_task_create(
            conn, title="WL probe", swimlane="core", kind="feature", outcome="parse work log."
        )
    )
    tid = created["data"]["task_id"]
    rel = created["data"]["file_path"]
    mcp_tools.cos_work_log_append(conn, task_id=tid, summary="first note")
    mcp_tools.cos_work_log_append(conn, task_id=tid, summary="second note abc1234")

    events = mcp_tools._worklog_events(rel)

    assert len(events) == 2
    assert all(e["type"] == "worklog" for e in events)
    assert events[0]["text"].startswith("first note")
    assert events[1]["text"].startswith("second note")
    assert events[0]["at"] <= events[1]["at"]  # +i keeps file order under the sort
    assert events[0]["actor"]["label"]  # actor-attributed, not blank


def test_worklog_events_empty_when_no_work_log(project: Path, conn: sqlite3.Connection):
    created = _parse(
        mcp_tools.cos_task_create(
            conn, title="No log", swimlane="core", kind="feature", outcome="no work log yet."
        )
    )
    assert mcp_tools._worklog_events(created["data"]["file_path"]) == []


# ---------- cos_task_retro envelope budget (TASK-336) ----------


class TestRetroEnvelopeBudget:
    def test_retro_stays_under_budget_on_300_completions(self, project, conn):
        import time as _t

        now = int(_t.time())
        rows = [
            (
                f"TASK-{900 + i}",
                f"retro budget seed task {i} " + "padding " * 30,
                "complete",
                f"docs/tasks/TASK-{900 + i}-seed.md",
                "",
                0,
                "core",
                "chore",
                "P3",
                now - 3600,
                now - 600 - i,
            )
            for i in range(300)
        ]
        conn.executemany(
            "INSERT OR REPLACE INTO tasks (task_id, title, status, file_path, "
            "content_hash, mtime, swimlane, kind, priority, started_at, completed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()

        envelope = mcp_tools.cos_task_retro(conn, since="7d")
        assert len(envelope) < 32_000, f"retro envelope {len(envelope)} chars"

        data = json.loads(envelope)["data"]
        assert data["completed_count"] >= 300
        assert len(data["completed"]) <= 25
        assert data["next_cursor"], "300 rows must paginate"
        assert data["swimlane_throughput"]["core"] >= 300

    def test_retro_cursor_walks_the_tail(self, project, conn):
        first = json.loads(mcp_tools.cos_task_retro(conn, since="7d", page_size=5))["data"]
        if not first["next_cursor"]:
            return  # tiny board — nothing to walk
        second = json.loads(
            mcp_tools.cos_task_retro(conn, since="7d", page_size=5, cursor=first["next_cursor"])
        )["data"]
        first_ids = {c["id"] for c in first["completed"]}
        second_ids = {c["id"] for c in second["completed"]}
        assert not (first_ids & second_ids), "pages must not overlap"
