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


def test_ready_gate_blocks_unready_icebox(conn: sqlite3.Connection):
    _insert_task(conn, "TASK-RG1", status="icebox", labels=[])
    result = transition(conn, "TASK-RG1", "in_progress", config=_make_config(in_progress=10))
    assert result.ok is False
    assert result.error_category == "validation"
    assert "not ready" in (result.error or "")


def test_ready_gate_allows_ready_icebox(conn: sqlite3.Connection):
    _insert_task(conn, "TASK-RG2", status="icebox", labels=["ready"])
    result = transition(conn, "TASK-RG2", "in_progress", config=_make_config(in_progress=10))
    assert result.ok, result.error


def test_ready_gate_exempts_emergency_path(conn: sqlite3.Connection):
    # emergency→in_progress is the fast lane — no ready label required.
    _insert_task(conn, "TASK-RG3", status="emergency", labels=[])
    result = transition(conn, "TASK-RG3", "in_progress", config=_make_config(in_progress=10))
    assert result.ok, result.error


def test_ready_gate_skipped_without_config(conn: sqlite3.Connection):
    # DB-only path (config=None) must not enforce policy.
    _insert_task(conn, "TASK-RG4", status="icebox", labels=[])
    result = transition(conn, "TASK-RG4", "in_progress")
    assert result.ok, result.error


def test_testing_gate_blocks_in_progress_to_complete(conn: sqlite3.Connection):
    _insert_task(conn, "TASK-TG1", status="in_progress")
    result = transition(conn, "TASK-TG1", "complete", config=_make_config())
    assert result.ok is False
    assert result.error_category == "validation"
    assert "through testing" in (result.error or "")


def test_testing_gate_allows_testing_to_complete(conn: sqlite3.Connection):
    _insert_task(conn, "TASK-TG2", status="testing")
    result = transition(conn, "TASK-TG2", "complete", config=_make_config())
    assert result.ok, result.error


def test_testing_gate_force_overrides(conn: sqlite3.Connection):
    _insert_task(conn, "TASK-TG3", status="in_progress")
    result = transition(conn, "TASK-TG3", "complete", config=_make_config(), force=True)
    assert result.ok, result.error


def test_skip_testing_warning_emitted_on_shortcut(
    tmp_path: Path,
    conn: sqlite3.Connection,
):
    """in_progress→complete is legal but unconventional — the caller
    must see a warning so the human can record verification in the
    work log if intentional. Guards docs/governance/task-lifecycle.md
    Core Loop contract."""
    (tmp_path / "docs" / "tasks").mkdir(parents=True)
    md = tmp_path / "docs" / "tasks" / "TASK-200-skip.md"
    md.write_text(
        '---\nid: TASK-200\ntitle: "s"\nswimlane: core\nkind: chore\n'
        'status: in_progress\npriority: P2\nappetite: "30m"\n---\n\n# TASK-200: s\n',
        encoding="utf-8",
    )
    sync_all(conn, project_root=tmp_path)
    result = transition(conn, "TASK-200", "complete")
    assert result.ok, result.error
    assert any("skipped 'testing'" in w for w in result.warnings), (
        f"expected skip-testing warning; got: {result.warnings}"
    )


def test_no_skip_testing_warning_on_canonical_path(
    tmp_path: Path,
    conn: sqlite3.Connection,
):
    """testing→complete is the canonical path — must NOT emit the
    skip-testing warning. False positives here would train agents to
    ignore the signal."""
    (tmp_path / "docs" / "tasks").mkdir(parents=True)
    md = tmp_path / "docs" / "tasks" / "TASK-201-canon.md"
    md.write_text(
        '---\nid: TASK-201\ntitle: "c"\nswimlane: core\nkind: chore\n'
        'status: testing\npriority: P2\nappetite: "30m"\n---\n\n# TASK-201: c\n',
        encoding="utf-8",
    )
    sync_all(conn, project_root=tmp_path)
    result = transition(conn, "TASK-201", "complete")
    assert result.ok, result.error
    assert not any("skipped 'testing'" in w for w in result.warnings), (
        f"false-positive skip-testing warning on testing→complete: {result.warnings}"
    )
