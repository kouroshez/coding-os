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
        Path(__file__).resolve().parents[2] / "thinking_os" / "db.py",
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
    return db.init_db(tmp_path / "thinking-os.db")


def _parse(envelope: str) -> dict:
    return json.loads(envelope)


# ---------- cos_task_create ----------


def test_create_task_happy_path(project: Path, conn: sqlite3.Connection):
    env = _parse(mcp_tools.cos_task_create(
        conn,
        title="Wire L.3 tools",
        swimlane="core",
        kind="feature",
        priority="P1",
        appetite="2h",
        labels=["mcp"],
        outcome="MCP tools importable and registered.",
    ))
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


def test_create_task_rejects_unknown_swimlane(project: Path, conn: sqlite3.Connection):
    env = _parse(mcp_tools.cos_task_create(
        conn, title="x", swimlane="nonexistent", kind="feature",
    ))
    assert env["ok"] is False
    assert env["error"]["category"] == "validation"
    assert "not in config" in env["error"]["message"]


def test_create_task_rejects_bad_kind(project: Path, conn: sqlite3.Connection):
    env = _parse(mcp_tools.cos_task_create(
        conn, title="x", swimlane="core", kind="invalid",
    ))
    assert env["ok"] is False
    assert env["error"]["category"] == "validation"


def test_create_task_rejects_label_colliding_with_kind(
    project: Path, conn: sqlite3.Connection,
):
    env = _parse(mcp_tools.cos_task_create(
        conn, title="x", swimlane="core", kind="feature", labels=["bug"],
    ))
    assert env["ok"] is False
    assert "collides with KIND_ENUM" in env["error"]["message"]


def test_create_task_auto_increments_id(project: Path, conn: sqlite3.Connection):
    e1 = _parse(mcp_tools.cos_task_create(
        conn, title="first", swimlane="core", kind="chore",
    ))
    e2 = _parse(mcp_tools.cos_task_create(
        conn, title="second", swimlane="core", kind="chore",
    ))
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
        conn, title="one", swimlane="core", kind="feature",
    )
    mcp_tools.cos_task_create(
        conn, title="two", swimlane="docs", kind="docs",
    )
    env = _parse(mcp_tools.cos_task_board(conn))
    assert env["ok"] is True
    assert env["data"]["count"] == 2
    assert "core" in env["data"]["grouped"]
    assert "docs" in env["data"]["grouped"]


def test_board_filters_by_swimlane(project: Path, conn: sqlite3.Connection):
    mcp_tools.cos_task_create(
        conn, title="a", swimlane="core", kind="feature",
    )
    mcp_tools.cos_task_create(
        conn, title="b", swimlane="docs", kind="docs",
    )
    env = _parse(mcp_tools.cos_task_board(conn, swimlane="core"))
    assert env["data"]["count"] == 1
    assert env["data"]["cards"][0]["swimlane"] == "core"


# ---------- cos_task_move ----------


def test_move_happy_path(project: Path, conn: sqlite3.Connection):
    _parse(mcp_tools.cos_task_create(
        conn, title="move me", swimlane="core", kind="feature",
    ))
    # icebox → ready
    env = _parse(mcp_tools.cos_task_move(conn, task_id="TASK-001", to="ready"))
    assert env["ok"] is True
    assert env["data"]["previous_status"] == "icebox"
    assert env["data"]["new_status"] == "ready"


def test_reposition_swimlane_only(project: Path, conn: sqlite3.Connection):
    _parse(mcp_tools.cos_task_create(
        conn, title="lane test", swimlane="core", kind="feature",
    ))
    env = _parse(
        mcp_tools.cos_task_reposition(
            conn, task_id="TASK-001", swimlane="docs",
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
    _parse(mcp_tools.cos_task_create(
        conn, title="both", swimlane="core", kind="chore",
    ))
    env = _parse(
        mcp_tools.cos_task_reposition(
            conn, task_id="TASK-001", to="ready", swimlane="docs",
        )
    )
    assert env["ok"] is True
    assert env["data"]["new_status"] == "ready"
    assert env["data"]["new_swimlane"] == "docs"
    row = conn.execute(
        "SELECT status, swimlane FROM tasks WHERE task_id = ?",
        ("TASK-001",),
    ).fetchone()
    assert row[0] == "ready"
    assert row[1] == "docs"


def test_move_wip_cap_rejection(project: Path, conn: sqlite3.Connection):
    # cap=2 per fixture; make 2 in_progress then try 3rd.
    for i in range(3):
        mcp_tools.cos_task_create(
            conn, title=f"t{i}", swimlane="core", kind="chore",
        )
    for tid in ("TASK-001", "TASK-002"):
        mcp_tools.cos_task_move(conn, task_id=tid, to="ready")
        mcp_tools.cos_task_move(conn, task_id=tid, to="in_progress")
    mcp_tools.cos_task_move(conn, task_id="TASK-003", to="ready")
    env = _parse(mcp_tools.cos_task_move(conn, task_id="TASK-003", to="in_progress"))
    assert env["ok"] is False
    assert "WIP cap" in env["error"]["message"]


# ---------- cos_task_pick ----------


def test_pick_returns_ready_tasks(project: Path, conn: sqlite3.Connection):
    mcp_tools.cos_task_create(
        conn, title="low", swimlane="core", kind="chore", priority="P3",
    )
    mcp_tools.cos_task_create(
        conn, title="high", swimlane="core", kind="feature", priority="P0",
    )
    mcp_tools.cos_task_move(conn, task_id="TASK-001", to="ready")
    mcp_tools.cos_task_move(conn, task_id="TASK-002", to="ready")

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
    _parse(mcp_tools.cos_task_create(
        conn, title="log me", swimlane="core", kind="feature",
    ))
    env = _parse(mcp_tools.cos_work_log_append(
        conn, task_id="TASK-001", summary="did a thing",
        agent_session="ses-claude-xyz",
    ))
    assert env["ok"] is True

    md_path = project / "docs" / "tasks" / "TASK-001-log-me.md"
    content = md_path.read_text(encoding="utf-8")
    assert "did a thing" in content
    assert "## Work Log" in content


def test_work_log_truncates_long_summary(
    project: Path, conn: sqlite3.Connection,
):
    mcp_tools.cos_task_create(
        conn, title="trunc", swimlane="core", kind="chore",
    )
    long_summary = "x" * 500
    env = _parse(mcp_tools.cos_work_log_append(
        conn, task_id="TASK-001", summary=long_summary,
    ))
    assert env["ok"] is True
    # Line should be ≤ 120 chars of summary
    line = env["data"]["line_appended"]
    # Format: "- YYYY-MM-DD [agent]: xxx"
    summary_part = line.split(": ", 1)[1]
    assert len(summary_part) <= 120


# ---------- cos_task_daily ----------


def test_daily_shape(project: Path, conn: sqlite3.Connection):
    mcp_tools.cos_task_create(
        conn, title="a", swimlane="core", kind="chore",
    )
    mcp_tools.cos_task_move(conn, task_id="TASK-001", to="ready")
    mcp_tools.cos_task_move(conn, task_id="TASK-001", to="in_progress")

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
