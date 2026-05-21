"""Tests for core/web/routes/stream.py — SSE dedup + attribution.

PURPOSE: Guard the stream so a single `cos task-move` produces exactly one
         event (the DB one), and a raw file edit produces exactly one
         event with agent_session=null (human attribution).
INPUT:   Synthetic tmp project — tmp sqlite DB + docs/tasks directory.
OUTPUT:  Asserts on the events pulled out of _event_generator().
NOTES:   The generator is an infinite poll loop.  We patch asyncio.sleep
         so each sleep tick lets the test inject state and abort after
         a bounded number of iterations.
"""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from thinking_os.database import init_db  # noqa: E402


@pytest.fixture
def cos_project(tmp_path, monkeypatch):
    """Materialise a fake coding-os project on disk."""
    project = tmp_path / "fake-project"
    (project / ".coding-os").mkdir(parents=True)
    (project / "docs" / "tasks").mkdir(parents=True)
    db = project / ".coding-os" / "coding-os.db"
    conn = init_db(db)
    conn.close()

    monkeypatch.setenv("COS_PROJECT_ROOT", str(project))
    monkeypatch.setenv("COS_DB_PATH", str(db))
    monkeypatch.setenv("COS_WEB_SSE_POLL_MS", "500")
    return project


def _write_task_file(project: Path, task_id: str, status: str = "ready", extra: str = "") -> Path:
    path = project / "docs" / "tasks" / f"{task_id}-slug.md"
    path.write_text(
        f"---\ntask_id: {task_id}\nstatus: {status}\n{extra}---\n\nbody\n",
        encoding="utf-8",
    )
    return path


def _insert_transition(
    db: Path,
    task_id: str,
    new_status: str,
    agent: str | None,
    ts: int,
    old_status: str = "icebox",
) -> None:
    conn = sqlite3.connect(str(db))
    try:
        conn.execute(
            """
            INSERT INTO task_status_history
                (task_id, old_status, new_status, agent_session,
                 reason, transitioned_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (task_id, old_status, new_status, agent, None, ts),
        )
        conn.commit()
    finally:
        conn.close()


async def _run_scenario(on_poll, max_polls: int = 5, want_events: int = 1) -> list[dict]:
    """Drive the SSE generator through a bounded set of polls.

    on_poll(poll_num) is awaited on each sleep before the generator
    resumes, letting the test inject DB rows / file changes between
    iterations.  Returns the list of parsed task-updated payloads.
    """
    from web.routes import stream as stream_mod

    polls = [0]

    async def _instant_sleep(delay):
        polls[0] += 1
        await on_poll(polls[0])
        if polls[0] >= max_polls:
            raise asyncio.CancelledError()

    original_sleep = asyncio.sleep
    asyncio.sleep = _instant_sleep  # type: ignore[assignment]
    events: list[dict] = []
    try:
        gen = stream_mod._event_generator()
        try:
            async for chunk in gen:
                text = chunk if isinstance(chunk, str) else chunk.decode()
                for block in text.strip().split("\n\n"):
                    if "event: task-updated" not in block:
                        continue
                    data_line = next(
                        (ln for ln in block.splitlines() if ln.startswith("data: ")),
                        None,
                    )
                    if data_line:
                        events.append(json.loads(data_line[len("data: ") :]))
                if len(events) >= want_events and polls[0] >= max_polls - 1:
                    break
        except asyncio.CancelledError:
            pass
    finally:
        asyncio.sleep = original_sleep  # type: ignore[assignment]
    return events


def test_db_transition_emits_with_agent_attribution(cos_project):
    """A DB row inserted after init surfaces with its agent_session intact."""
    db = cos_project / ".coding-os" / "coding-os.db"
    _write_task_file(cos_project, "TASK-001", status="in_progress")

    async def on_poll(poll_num: int) -> None:
        if poll_num == 1:
            # Insert between init (which snapshots MAX(id)) and first poll body.
            _insert_transition(
                db,
                "TASK-001",
                "in_progress",
                "ses-claude-test",
                ts=1_700_000_000,
            )

    events = asyncio.run(_run_scenario(on_poll, max_polls=4, want_events=1))
    db_events = [e for e in events if e["task_id"] == "TASK-001" and e.get("source") == "db"]
    assert db_events, f"expected a DB-sourced event; got {events}"
    assert db_events[0]["agent_session"] == "ses-claude-test"
    assert db_events[0]["new_status"] == "in_progress"


def test_file_edit_without_db_row_is_human(cos_project):
    """A raw mtime change with no matching DB row must attribute to human."""
    import time as _time

    path = _write_task_file(cos_project, "TASK-002", status="ready")

    async def on_poll(poll_num: int) -> None:
        if poll_num == 2:
            # Poll #1 establishes mtime baseline; poll #2 mutates the file
            # (with a stale agent_session in the frontmatter) so poll #3 detects it.
            path.write_text(
                "---\ntask_id: TASK-002\nstatus: testing\n"
                "agent_session: ses-stale-claude\n---\nbody2\n",
                encoding="utf-8",
            )
            now = _time.time()
            os.utime(path, (now, now))

    events = asyncio.run(_run_scenario(on_poll, max_polls=5, want_events=1))
    matching = [e for e in events if e["task_id"] == "TASK-002"]
    assert matching, f"expected a task-updated for TASK-002; got {events}"
    ev = matching[0]
    # Frontmatter said "ses-stale-claude", but no DB row aligns with the
    # mtime: the event must attribute to human (null agent_session).
    assert ev["agent_session"] is None
    assert ev.get("source") == "file"


def test_db_event_suppresses_duplicate_file_event(cos_project):
    """A DB row aligned with a file mtime must suppress the file event."""
    import time as _time

    db = cos_project / ".coding-os" / "coding-os.db"
    path = _write_task_file(cos_project, "TASK-003", status="ready")

    async def on_poll(poll_num: int) -> None:
        if poll_num == 2:
            # Simulate `cos task-move`: file + DB row both mutate at `now`.
            now = int(_time.time())
            path.write_text(
                "---\ntask_id: TASK-003\nstatus: in_progress\n---\nbody2\n",
                encoding="utf-8",
            )
            os.utime(path, (now, now))
            _insert_transition(
                db,
                "TASK-003",
                "in_progress",
                "ses-cursor-t",
                ts=now,
            )

    events = asyncio.run(_run_scenario(on_poll, max_polls=5, want_events=2))
    matching = [e for e in events if e["task_id"] == "TASK-003"]
    assert len(matching) == 1, f"expected exactly one event for TASK-003; got {matching}"
    assert matching[0]["source"] == "db"
    assert matching[0]["agent_session"] == "ses-cursor-t"
