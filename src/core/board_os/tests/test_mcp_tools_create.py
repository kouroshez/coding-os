"""Tests for core.board_os.mcp_tools — L.3 MCP surface."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import yaml

from core.board_os import mcp_tools

from .conftest import _parse


def test_create_task_happy_path(project: Path, conn: sqlite3.Connection):
    env = _parse(
        mcp_tools.cos_task_create(
            conn,
            title="Wire L.3 tools",
            swimlane="core",
            kind="feature",
            priority="P1",
            appetite="2h",
            labels=["mcp"],
            outcome="MCP tools importable and registered.",
        )
    )
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


def test_create_task_title_with_double_quote_stays_valid_yaml(
    project: Path, conn: sqlite3.Connection
):
    # Regression: a title containing a double-quote must render
    # valid YAML so the task stays editable through the semantic ops.
    env = _parse(
        mcp_tools.cos_task_create(
            conn,
            title='Fix "ready" gate',
            swimlane="core",
            kind="bug",
            outcome="Quoted title round-trips through YAML.",
        )
    )
    assert env["ok"] is True
    task_id = env["data"]["task_id"]
    content = (project / env["data"]["file_path"]).read_text(encoding="utf-8")

    parsed = yaml.safe_load(content.split("---", 2)[1])
    assert parsed["title"] == 'Fix "ready" gate'

    # Editable via the semantic op — would fail with 'not in lean frontmatter
    # format' if the YAML were broken by an unescaped inner quote.
    edited = _parse(mcp_tools.cos_task_edit(conn, task_id=task_id, priority="P0"))
    assert edited["ok"] is True


def test_create_attributes_human_when_session_is_human(project, conn):
    # The web manual-create path passes agent_session='human' so a
    # human-made task is attributed to the human, not the active agent panel.
    created = _parse(
        mcp_tools.cos_task_create(
            conn,
            title="Made by a human",
            swimlane="core",
            kind="feature",
            outcome="A human-made task.",
            agent_session="human",
        )
    )
    hist = _parse(mcp_tools.cos_task_history(conn, task_id=created["data"]["task_id"]))
    assert hist["ok"] is True
    assert hist["data"]["summary"]["created_by"] == "human"


def test_create_attributes_agent_when_session_is_agent(project, conn):
    created = _parse(
        mcp_tools.cos_task_create(
            conn,
            title="Made by an agent",
            swimlane="core",
            kind="feature",
            outcome="An agent-made task.",
            agent_session="ses-claude-20260605-185000-zzzz",
        )
    )
    hist = _parse(mcp_tools.cos_task_history(conn, task_id=created["data"]["task_id"]))
    assert hist["data"]["summary"]["created_by"] == "claude"


def test_create_task_in_progress_stamps_started_and_session(
    project: Path, conn: sqlite3.Connection
):
    """F17 / TASK-029 task-lifecycle: creating a task directly in
    `in_progress` used to leave `started` and `agent_session` null in
    the YAML frontmatter — the DB row had values but the file did
    not. After fix both layers agree on creation."""
    env = _parse(
        mcp_tools.cos_task_create(
            conn,
            title="In-progress at creation",
            swimlane="core",
            kind="feature",
            status="in_progress",
            outcome="Stamp started + agent_session when a task is created directly in progress.",
            acceptance=(
                "- **Given** a task created with status=in_progress\n"
                "- **When** the create completes\n"
                "- **Then** started and agent_session are non-null in the file."
            ),
            agent_session="ses-test-lifecycle-1",
        )
    )
    assert env["ok"] is True
    md = project / env["data"]["file_path"]
    content = md.read_text(encoding="utf-8")
    assert "started: null" not in content
    assert "agent_session: null" not in content
    assert "ses-test-lifecycle-1" in content


def test_create_task_testing_does_not_stamp_started(project: Path, conn: sqlite3.Connection):
    """F17b: only `in_progress` stamps `started` at create-time to
    match `workflow.transition` semantics. Tasks created directly in
    `testing` / `emergency` are unusual and should reach those states
    via transition; keep create-path conservative so the two layers
    do not diverge."""
    env = _parse(
        mcp_tools.cos_task_create(
            conn,
            title="Created in testing",
            swimlane="core",
            kind="feature",
            status="testing",
            agent_session="ses-test-lifecycle-2",
        )
    )
    assert env["ok"] is True
    md = project / env["data"]["file_path"]
    content = md.read_text(encoding="utf-8")
    assert "started: null" in content
    assert "agent_session: null" in content


def test_create_task_rejects_unknown_swimlane(project: Path, conn: sqlite3.Connection):
    env = _parse(
        mcp_tools.cos_task_create(
            conn,
            title="x",
            swimlane="nonexistent",
            kind="feature",
        )
    )
    assert env["ok"] is False
    assert env["error"]["category"] == "validation"
    assert "not in config" in env["error"]["message"]


def test_create_task_rejects_bad_kind(project: Path, conn: sqlite3.Connection):
    env = _parse(
        mcp_tools.cos_task_create(
            conn,
            title="x",
            swimlane="core",
            kind="invalid",
        )
    )
    assert env["ok"] is False
    assert env["error"]["category"] == "validation"


def test_create_task_rejects_label_colliding_with_kind(
    project: Path,
    conn: sqlite3.Connection,
):
    env = _parse(
        mcp_tools.cos_task_create(
            conn,
            title="x",
            swimlane="core",
            kind="feature",
            labels=["bug"],
        )
    )
    assert env["ok"] is False
    assert "collides with KIND_ENUM" in env["error"]["message"]


def test_create_task_auto_increments_id(project: Path, conn: sqlite3.Connection):
    e1 = _parse(
        mcp_tools.cos_task_create(
            conn,
            title="first",
            swimlane="core",
            kind="chore",
        )
    )
    e2 = _parse(
        mcp_tools.cos_task_create(
            conn,
            title="second",
            swimlane="core",
            kind="chore",
        )
    )
    assert e1["data"]["task_id"] == "TASK-001"
    assert e2["data"]["task_id"] == "TASK-002"
