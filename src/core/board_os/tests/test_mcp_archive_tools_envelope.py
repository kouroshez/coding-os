"""Archive drain, icebox sweep, reconciliation, and the board envelope budget."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from core.board_os import mcp_tools

from .conftest import _parse

_SL = [{"id": "core", "label": "Core", "color": "#3b82f6"}]


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
