"""cos_task_reclaim and the board time dimension (dwell, stale, widening)."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from core.board_os import mcp_tools

from .conftest import _backdate_task, _parse


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
        mcp_tools, "_commits_referencing_batch", lambda ids, *a, **k: dict.fromkeys(ids, 0)
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
        mcp_tools, "_commits_referencing_batch", lambda ids, *a, **k: dict.fromkeys(ids, 0)
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
