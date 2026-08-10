"""Archive drain, icebox sweep, reconciliation, and the board envelope budget."""

from __future__ import annotations

import json
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
