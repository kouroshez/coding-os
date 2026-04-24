"""Presence state machine: active / present / offline.

PURPOSE: Guard the 3-state presence model so the live-agents panel
         distinguishes "generating right now" from "session alive but
         thinking" from "not here".  Writes are driven by
         core/hooks/agent-presence.sh; reads are from board.py.
INPUT:   Synthetic tmp project with per-agent session JSON files.
OUTPUT:  Assertions on _presence_state for every state transition +
         PID-liveness fallback (crashed session).
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from core.web.routes import board as board_routes  # noqa: E402


@pytest.fixture
def fake_project(tmp_path, monkeypatch):
    project = tmp_path / "proj"
    (project / ".coding-os").mkdir(parents=True)
    monkeypatch.setenv("COS_PROJECT_ROOT", str(project))
    return project


def _write_presence(project: Path, agent: str, sid: str, **fields) -> Path:
    d = project / ".coding-os" / agent / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    payload = {
        "agent": agent,
        "session_id": sid,
        "pid": os.getpid(),  # our own pid = alive by construction
        "started_at": int(time.time()) - 60,
        "last_prompt_at": None,
        "last_tool_at": None,
        "last_stop_at": None,
        "ended_at": None,
        **fields,
    }
    path = d / f"{sid}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_no_sessions_returns_offline(fake_project):
    assert board_routes._presence_state("claude") == "offline"


def test_recent_tool_returns_active(fake_project):
    now = int(time.time())
    _write_presence(fake_project, "claude", "ses-claude-1", last_tool_at=now - 5)
    assert board_routes._presence_state("claude") == "active"


def test_old_tool_but_alive_returns_present(fake_project):
    now = int(time.time())
    _write_presence(
        fake_project, "claude", "ses-claude-2",
        last_tool_at=now - 120,       # outside ACTIVE window
        last_stop_at=now - 60,        # most recent "turn done"
        last_prompt_at=now - 300,     # older than stop
    )
    assert board_routes._presence_state("claude") == "present"


def test_user_turn_in_flight_is_active(fake_project):
    """A prompt newer than the last stop means the agent is still responding."""
    now = int(time.time())
    _write_presence(
        fake_project, "claude", "ses-claude-3",
        last_prompt_at=now - 40,      # new prompt arrived
        last_stop_at=now - 100,       # last stop was before that
        last_tool_at=now - 90,        # outside active window
    )
    assert board_routes._presence_state("claude") == "active"


def test_ended_session_is_offline(fake_project):
    now = int(time.time())
    _write_presence(
        fake_project, "claude", "ses-claude-4",
        last_tool_at=now - 5,
        ended_at=now - 1,
    )
    assert board_routes._presence_state("claude") == "offline"


def test_dead_pid_with_stale_heartbeat_is_offline(fake_project):
    """Dead pid AND no recent heartbeat = offline.  Both signals must be
    cold (>1h = past PRESENT window) before we declare offline; a recent
    heartbeat keeps the session alive regardless of pid because some
    runtimes rotate subprocesses between hook fires."""
    now = int(time.time())
    dead_pid = 2**31 - 1
    # Also bump started_at well past the PRESENT window so the
    # "session recently started" path can't save it either.
    _write_presence(
        fake_project, "claude", "ses-claude-dead",
        pid=dead_pid,
        started_at=now - 7200,
        last_tool_at=now - 7200,
        last_prompt_at=now - 7200,
        last_stop_at=now - 7200,
    )
    assert board_routes._presence_state("claude") == "offline"


def test_dead_pid_with_recent_heartbeat_is_active(fake_project):
    """Cursor / Claude Code VSCode rotate subprocesses between tool calls;
    the presence file's pid references one that already exited while the
    same session continues.  Heartbeat (last_tool_at) wins — without this,
    cursor kept showing 'offline' in the live-agents panel even while
    actively writing code."""
    now = int(time.time())
    dead_pid = 2**31 - 1
    _write_presence(
        fake_project, "cursor", "ses-cursor-subproc-rotated",
        pid=dead_pid,
        last_tool_at=now - 5,  # fresh heartbeat
    )
    assert board_routes._presence_state("cursor") == "active"


def test_multiple_sessions_pick_best(fake_project):
    """When one session is ACTIVE and another PRESENT, ACTIVE wins."""
    now = int(time.time())
    _write_presence(
        fake_project, "codex", "ses-codex-idle",
        last_tool_at=now - 200,
        last_stop_at=now - 100,
        last_prompt_at=now - 300,
    )
    _write_presence(
        fake_project, "codex", "ses-codex-active",
        last_tool_at=now - 3,
    )
    assert board_routes._presence_state("codex") == "active"


def test_agent_state_falls_back_to_db_as_present(fake_project, monkeypatch):
    """If the presence dir is empty but the DB has a recent transition,
    _agent_state reports 'present' — NOT 'active'.  Active is reserved
    for hook-backed real-time signals; a DB hit is a historical trace
    and shouldn't pulse the live-agents dot green."""
    import sqlite3

    from core.thinking_os.db import init_db

    db_path = fake_project / ".coding-os" / "thinking-os.db"
    init_db(db_path).close()
    monkeypatch.setenv("COS_DB_PATH", str(db_path))

    now = int(time.time())
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO task_status_history "
        "(task_id, old_status, new_status, agent_session, reason, transitioned_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("TASK-X", "icebox", "ready", "ses-cursor-legacy", None, now - 10),
    )
    conn.commit()
    try:
        assert board_routes._agent_state(conn, "cursor") == "present"
        assert board_routes._agent_state(conn, "claude") == "offline"
    finally:
        conn.close()
