"""cos_task_move, the learning-loop close, pick, wip, work-log, daily and retro."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from core.board_os import mcp_tools

from .conftest import _parse


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
