"""cos_task_move, the learning-loop close, pick, wip, work-log, daily and retro."""

from __future__ import annotations

import json
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
