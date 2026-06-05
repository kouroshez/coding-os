"""Tests for core.board_os.mcp_tools — L.3 MCP surface."""

from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
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
    assert env["data"]["grouped"] == {}
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
    assert "core" in env["data"]["grouped"]
    assert "docs" in env["data"]["grouped"]


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
    # force=True bypasses Phase L.10 DoR body gate; this test exercises
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
            agent_session="ses-cursor-20260423-abc",
        )
    )
    assert env["ok"] is True
    assert "[cursor]" in env["data"]["line_appended"]


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


# ---------- concurrent id allocation (TASK-088) ----------


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


# ---------- cos_task_reclaim (zombie recovery, TASK-089) ----------


def test_reclaim_moves_idle_in_progress_to_icebox_ready(project: Path, conn: sqlite3.Connection):
    import time as _t

    env = _parse(
        mcp_tools.cos_task_create(
            conn, title="zombie", swimlane="core", kind="chore",
            outcome="zombie reclaim regression guard outcome.", ready=True,
        )
    )
    tid = env["data"]["task_id"]
    assert _parse(mcp_tools.cos_task_move(conn, task_id=tid, to="in_progress", agent_session="ses-dead"))["ok"]

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
            conn, title="fresh", swimlane="core", kind="chore",
            outcome="fresh task must not be reclaimed outcome.", ready=True,
        )
    )
    tid = env["data"]["task_id"]
    assert _parse(mcp_tools.cos_task_move(conn, task_id=tid, to="in_progress", agent_session="ses-x"))["ok"]

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
        mcp_tools.cos_task_move(conn, task_id=task_id, to="in_progress", agent_session="ses-claude-hist")
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
    created = _parse(
        mcp_tools.cos_task_create(conn, title="Same", swimlane="core", kind="chore")
    )
    tid = created["data"]["task_id"]
    env = _parse(mcp_tools.cos_task_edit(conn, task_id=tid, title="Same"))
    assert env["ok"] is True
    assert env["data"]["changed"] == []


def test_task_edit_rejects_bad_swimlane(project: Path, conn: sqlite3.Connection):
    created = _parse(
        mcp_tools.cos_task_create(conn, title="x", swimlane="core", kind="chore")
    )
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
    conn.execute("UPDATE task_status_history SET transitioned_at = ? WHERE task_id = ?", (old, ztid))
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
