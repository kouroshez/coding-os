"""Tests for core.board_os.sync — task file → DB sync (L.1)."""

from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest

from core.board_os.sync import sync_all, sync_one


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


LEAN_TASK = """---
id: TASK-042
title: "Sync fixture task"
swimlane: core
kind: feature
epic: phase-l
labels: [sync, fixture]
status: in_progress
priority: P1
appetite: "2h"
created: 2026-04-20
started: 2026-04-20
completed: null
depends_on: [TASK-001]
blocked_by: []
references: []
---

# TASK-042: Sync fixture task

**Outcome (one sentence):** Database rows reflect frontmatter.

## Read First
- [docs/phase-l-scrumban-task-system-plan.md](../phase-l.md)

## Acceptance (G/W/T)
- **Given** sync runs
- **When** task file written
- **Then** row exists in tasks table

## Work Log
- 2026-04-20 [claude]: initial commit
- 2026-04-20 [claude]: parser wired
"""


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "docs" / "tasks").mkdir(parents=True)
    (tmp_path / "docs" / "tasks" / "TASK-042-sync-fixture.md").write_text(
        LEAN_TASK, encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    return db.init_db(tmp_path / "coding-os.db")


def test_sync_all_upserts_new_task(project: Path, conn: sqlite3.Connection):
    stats = sync_all(conn, project_root=project)
    assert stats["upserted"] == 1
    assert stats["parse_errors"] == 0

    row = conn.execute(
        "SELECT task_id, swimlane, kind, epic, priority, appetite, status "
        "FROM tasks WHERE task_id = 'TASK-042'"
    ).fetchone()
    assert row is not None
    assert row[0] == "TASK-042"
    assert row[1] == "core"
    assert row[2] == "feature"
    assert row[3] == "phase-l"
    assert row[4] == "P1"
    assert row[5] == "2h"
    assert row[6] == "in_progress"


def test_sync_writes_labels_json_and_work_log(project: Path, conn: sqlite3.Connection):
    sync_all(conn, project_root=project)
    row = conn.execute(
        "SELECT labels_json, work_log_last_5 FROM tasks WHERE task_id = 'TASK-042'"
    ).fetchone()
    assert row is not None
    assert json.loads(row[0]) == ["sync", "fixture"]
    log = json.loads(row[1])
    assert len(log) == 2
    assert "initial commit" in log[0]
    assert "parser wired" in log[1]


def test_sync_skips_unchanged_file(project: Path, conn: sqlite3.Connection):
    sync_all(conn, project_root=project)
    stats = sync_all(conn, project_root=project)
    assert stats["skipped_unchanged"] == 1
    assert stats["upserted"] == 0


def test_sync_one_records_status_change(project: Path, conn: sqlite3.Connection):
    sync_all(conn, project_root=project)
    task_file = project / "docs" / "tasks" / "TASK-042-sync-fixture.md"
    # Edit status icebox → ... in the existing file (simulate move)
    updated = task_file.read_text(encoding="utf-8").replace(
        "status: in_progress", "status: testing"
    )
    task_file.write_text(updated, encoding="utf-8")

    sync_one(conn, task_file, project_root=project)

    history = conn.execute(
        "SELECT old_status, new_status FROM task_status_history "
        "WHERE task_id = 'TASK-042' ORDER BY transitioned_at"
    ).fetchall()
    assert len(history) >= 1
    assert history[-1][0] == "in_progress"
    assert history[-1][1] == "testing"


def test_sync_missing_docs_tasks_dir(tmp_path: Path, conn: sqlite3.Connection):
    """Zero-file repo still syncs cleanly."""
    stats = sync_all(conn, project_root=tmp_path)
    assert stats == {"scanned": 0, "upserted": 0, "skipped_unchanged": 0, "parse_errors": 0}


def test_sync_one_on_lean_task_writes_epic(project: Path, conn: sqlite3.Connection):
    task_file = project / "docs" / "tasks" / "TASK-042-sync-fixture.md"
    parsed = sync_one(conn, task_file, project_root=project)
    assert parsed is not None
    assert parsed.epic == "phase-l"

    row = conn.execute(
        "SELECT epic FROM tasks WHERE task_id = 'TASK-042'"
    ).fetchone()
    assert row[0] == "phase-l"
