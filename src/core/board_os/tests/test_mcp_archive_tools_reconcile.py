"""Archive drain, icebox sweep, reconciliation, and the board envelope budget."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from core.board_os import mcp_tools

from .conftest import _backdate_task, _parse

_SL = [{"id": "core", "label": "Core", "color": "#3b82f6"}]


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
        mcp_tools, "_commits_referencing_batch", lambda ids, *a, **k: dict.fromkeys(ids, 0)
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
        mcp_tools, "_commits_referencing_batch", lambda ids, *a, **k: dict.fromkeys(ids)
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
        mcp_tools, "_commits_referencing_batch", lambda ids, *a, **k: dict.fromkeys(ids, 1)
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
        mcp_tools, "_commits_referencing_batch", lambda ids, *a, **k: dict.fromkeys(ids, 1)
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
