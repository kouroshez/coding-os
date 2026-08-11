"""Tests for core.board_os.workflow — L.2 state machine + WIP + cycles."""

from __future__ import annotations

import importlib.util
import json
import sqlite3
import time
from pathlib import Path

import pytest

from core.board_os.config import ScrumbanConfig, Swimlane, WipLimits
from core.board_os.workflow import (
    _is_shared_pid_session,
    check_wip,
    transition,
)


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


def _make_config(in_progress: int = 1, testing: int = 3, emergency: int = 2):
    return ScrumbanConfig(
        swimlanes=(Swimlane(id="core", label="Core", color="#3b82f6"),),
        wip_limits=WipLimits(
            in_progress=in_progress,
            testing=testing,
            emergency=emergency,
        ),
    )


def _insert_task(
    conn: sqlite3.Connection,
    task_id: str,
    *,
    status: str = "icebox",
    swimlane: str = "core",
    depends_on: list[str] | None = None,
    labels: list[str] | None = None,
    agent_session: str | None = None,
) -> None:
    # Default to a `ready`-labelled task: most state-machine/WIP tests
    # need a pullable task, matching the require_ready_label contract.
    # Pass labels=[] to exercise the not-ready path.
    labels = ["ready"] if labels is None else labels
    conn.execute(
        "INSERT INTO tasks (task_id, title, status, file_path, content_hash, "
        "mtime, swimlane, kind, priority, appetite, labels_json, dependencies, agent_session) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            task_id,
            f"test {task_id}",
            status,
            f"docs/tasks/{task_id}.md",
            "abc",
            int(time.time()),
            swimlane,
            "chore",
            "P2",
            "1h",
            json.dumps(labels),
            json.dumps(depends_on or []),
            agent_session,
        ),
    )
    conn.commit()


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    return db.init_db(tmp_path / "coding-os.db")


# ---------- Valid transitions ----------


def test_force_bypasses_wip_cap(conn: sqlite3.Connection):
    """force=True is a superset of bypass_wip — a single flag covers both."""
    _insert_task(conn, "TASK-F2", status="icebox")
    _insert_task(conn, "TASK-F3", status="in_progress")  # already at cap=1
    blocked = transition(
        conn,
        "TASK-F2",
        "in_progress",
        config=_make_config(in_progress=1),
    )
    assert blocked.ok is False
    assert "WIP cap" in (blocked.error or "")

    forced = transition(
        conn,
        "TASK-F2",
        "in_progress",
        force=True,
        config=_make_config(in_progress=1),
    )
    assert forced.ok, forced.error
    assert forced.new_status == "in_progress"


def test_wip_cap_blocks_second_in_progress(conn: sqlite3.Connection):
    _insert_task(conn, "TASK-010", status="in_progress")
    _insert_task(conn, "TASK-011", status="icebox")
    config = _make_config(in_progress=1)
    result = transition(conn, "TASK-011", "in_progress", config=config)
    assert result.ok is False
    assert "WIP cap" in (result.error or "")


def test_wip_cap_allows_within_limit(conn: sqlite3.Connection):
    _insert_task(conn, "TASK-012", status="icebox")
    config = _make_config(in_progress=1)
    result = transition(conn, "TASK-012", "in_progress", config=config)
    assert result.ok is True


def test_wip_bypass_flag_overrides_cap(conn: sqlite3.Connection):
    _insert_task(conn, "TASK-013", status="in_progress")
    _insert_task(conn, "TASK-014", status="icebox")
    config = _make_config(in_progress=1)
    result = transition(
        conn,
        "TASK-014",
        "in_progress",
        config=config,
        bypass_wip=True,
    )
    assert result.ok is True


def test_check_wip_reports_counts_and_caps(conn: sqlite3.Connection):
    _insert_task(conn, "TASK-020", status="in_progress")
    _insert_task(conn, "TASK-021", status="testing")
    _insert_task(conn, "TASK-022", status="testing")
    config = _make_config(in_progress=1, testing=3, emergency=2)
    state = check_wip(conn, config)
    assert state.counts["in_progress"] == 1
    assert state.counts["testing"] == 2
    assert state.counts["emergency"] == 0
    assert state.caps["testing"] == 3


def test_per_session_wip_does_not_block_other_session(conn: sqlite3.Connection):
    # Session A holds an in_progress task; session B (different
    # agent_session) must still be able to start its own.
    _insert_task(conn, "TASK-PA", status="in_progress", agent_session="ses-A")
    _insert_task(conn, "TASK-PB", status="icebox", agent_session="ses-B")
    result = transition(
        conn,
        "TASK-PB",
        "in_progress",
        config=_make_config(in_progress=1),
        agent_session="ses-B",
    )
    assert result.ok, result.error


def test_per_session_wip_still_blocks_same_session(conn: sqlite3.Connection):
    # The same session is still capped at 1 (focus discipline).
    _insert_task(conn, "TASK-SA1", status="in_progress", agent_session="ses-A")
    _insert_task(conn, "TASK-SA2", status="icebox", agent_session="ses-A")
    result = transition(
        conn,
        "TASK-SA2",
        "in_progress",
        config=_make_config(in_progress=1),
        agent_session="ses-A",
    )
    assert result.ok is False
    assert "WIP cap" in (result.error or "")


def test_global_wip_when_per_session_disabled(conn: sqlite3.Connection):
    from core.board_os.config import ScrumbanConfig, Swimlane, WipLimits, WorkflowPolicy

    cfg = ScrumbanConfig(
        swimlanes=(Swimlane(id="core", label="Core", color="#3b82f6"),),
        wip_limits=WipLimits(in_progress=1),
        workflow_policy=WorkflowPolicy(per_session_wip=False),
    )
    _insert_task(conn, "TASK-GA", status="in_progress", agent_session="ses-A")
    _insert_task(conn, "TASK-GB", status="icebox", agent_session="ses-B")
    result = transition(conn, "TASK-GB", "in_progress", config=cfg, agent_session="ses-B")
    assert result.ok is False
    assert "WIP cap" in (result.error or "")


def test_is_shared_pid_session_detects_synthetic() -> None:
    # The resolve_agent_session last-resort synthetic — shared by all panels
    # of the long-lived MCP server — must be recognised.
    assert _is_shared_pid_session("ses-claude-pid12345") is True
    assert _is_shared_pid_session("ses-codex-pid7") is True
    # Genuine per-panel session ids and non-sessions must NOT match.
    assert _is_shared_pid_session("ses-claude-20260609-143642-c7c5") is False
    assert _is_shared_pid_session("ses-claude-pid12-extra") is False
    assert _is_shared_pid_session(None) is False
    assert _is_shared_pid_session("") is False


def test_shared_pid_session_warns_wip_degraded(conn: sqlite3.Connection, caplog) -> None:
    # A per-session cap keyed on the shared ses-<agent>-pid<PID> synthetic must
    # be surfaced (not silently applied as if it were panel-isolated).
    _insert_task(conn, "TASK-SP", status="in_progress", agent_session="ses-claude-pid99999")
    with caplog.at_level("WARNING"):
        check_wip(conn, _make_config(in_progress=1), agent_session="ses-claude-pid99999")
    assert "WIP cap degraded" in caplog.text
    assert "ses-claude-pid99999" in caplog.text


def test_real_session_no_wip_degraded_warning(conn: sqlite3.Connection, caplog) -> None:
    _insert_task(
        conn, "TASK-RS", status="in_progress", agent_session="ses-claude-20260609-143642-c7c5"
    )
    with caplog.at_level("WARNING"):
        check_wip(
            conn, _make_config(in_progress=1), agent_session="ses-claude-20260609-143642-c7c5"
        )
    assert "WIP cap degraded" not in caplog.text
