"""Tests for core.board_os.workflow — L.2 state machine + WIP + cycles."""

from __future__ import annotations

import importlib.util
import json
import sqlite3
import time
from pathlib import Path

import pytest

from core.board_os.config import ScrumbanConfig, Swimlane, WipLimits
from core.board_os.sync import sync_all
from core.board_os.workflow import (
    patch_task_frontmatter_scalars,
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


def test_transition_updates_md_frontmatter(tmp_path: Path, conn: sqlite3.Connection):
    # Create a real MD file + sync it into DB first.
    (tmp_path / "docs" / "tasks").mkdir(parents=True)
    md = tmp_path / "docs" / "tasks" / "TASK-099-integration.md"
    md.write_text(
        "---\n"
        "id: TASK-099\n"
        'title: "integration"\n'
        "swimlane: core\n"
        "kind: chore\n"
        "status: icebox\n"
        "priority: P2\n"
        'appetite: "30m"\n'
        "labels: [ready]\n"
        "---\n\n"
        "# TASK-099: integration\n\n"
        "**Outcome (one sentence):** frontmatter round-trips.\n\n"
        "## Acceptance\n"
        "- **Given** transition runs\n"
        "- **When** status changes\n"
        "- **Then** file updated\n",
        encoding="utf-8",
    )
    sync_all(conn, project_root=tmp_path)

    result = transition(
        conn,
        "TASK-099",
        "in_progress",
        config=_make_config(in_progress=5),
        agent_session="ses-claude-test",
        file_path=md,
    )
    assert result.ok, result.error

    updated = md.read_text(encoding="utf-8")
    assert "status: in_progress" in updated
    assert "agent_session: ses-claude-test" in updated
    assert "started:" in updated


def test_transition_complete_sets_completed_at(
    tmp_path: Path,
    conn: sqlite3.Connection,
):
    (tmp_path / "docs" / "tasks").mkdir(parents=True)
    md = tmp_path / "docs" / "tasks" / "TASK-100-complete.md"
    md.write_text(
        '---\nid: TASK-100\ntitle: "c"\nswimlane: core\nkind: chore\n'
        'status: testing\npriority: P2\nappetite: "30m"\n---\n\n# TASK-100: c\n',
        encoding="utf-8",
    )
    sync_all(conn, project_root=tmp_path)
    result = transition(conn, "TASK-100", "complete")
    assert result.ok, result.error
    row = conn.execute("SELECT completed_at FROM tasks WHERE task_id = 'TASK-100'").fetchone()
    assert row[0] is not None


def test_patch_task_frontmatter_scalars_swimlane(tmp_path: Path):
    (tmp_path / "docs" / "tasks").mkdir(parents=True)
    md = tmp_path / "docs" / "tasks" / "TASK-101-swim.md"
    md.write_text(
        '---\nid: TASK-101\ntitle: "s"\nswimlane: core\nkind: chore\n'
        'status: icebox\npriority: P2\nappetite: "1d"\n---\n\n# TASK-101: s\n',
        encoding="utf-8",
    )
    patch_task_frontmatter_scalars(md, {"swimlane": "docs"})
    text = md.read_text(encoding="utf-8")
    assert "swimlane: docs" in text
    assert "status: icebox" in text


def test_transition_without_reason_synthesizes_source_tag(conn: sqlite3.Connection):
    """A history row must never carry a NULL reason — an unattributed backward
    move is unauditable (the phantom in_progress→icebox reverts)."""
    _insert_task(conn, "TASK-001", status="in_progress")
    result = transition(conn, "TASK-001", "icebox", bypass_gates=True)
    assert result.ok, result.error
    row = conn.execute(
        "SELECT reason FROM task_status_history WHERE task_id = 'TASK-001' "
        "ORDER BY transitioned_at DESC, rowid DESC LIMIT 1"
    ).fetchone()
    assert row is not None
    assert row[0], "reason must be non-empty"
    assert "unattributed" in row[0]
