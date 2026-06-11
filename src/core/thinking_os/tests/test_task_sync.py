"""
Tests for core/thinking_os/task_sync.py (compatibility shim, TASK-398)
and the board_os sync it delegates to.

Covers:
  - shim API surface: sync_tasks + the `sync` alias background.py calls
    (the alias was missing for months — background task-sync failed every
    tick with AttributeError; this is the regression guard)
  - lean-card sync happy path (statuses from frontmatter, no index file)
  - legacy stat aliases (new/errors/skipped)
  - force=True re-syncs an mtime-unchanged file
  - lean fields persisted: goal_text=outcome, blocked_by/references/
    external_ref, created_at from frontmatter, UPPERCASE domain
  - backward status move via file sync recorded as a sync-conflict
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import task_sync
from database import init_db


def _lean_card(
    task_id: str,
    title: str,
    *,
    swimlane: str = "backend",
    status: str = "icebox",
    outcome: str = "Something measurable.",
    depends_on: tuple[str, ...] = (),
    blocked_by: tuple[str, ...] = (),
    references: tuple[str, ...] = (),
    external_ref: str | None = None,
    created: str = "2026-06-01",
) -> str:
    deps = "[" + ", ".join(depends_on) + "]"
    blocked = "[" + ", ".join(blocked_by) + "]"
    refs = "[" + ", ".join(references) + "]"
    ext = f"external_ref: {external_ref}\n" if external_ref else ""
    return (
        "---\n"
        f"id: {task_id}\n"
        f'title: "{title}"\n'
        f"swimlane: {swimlane}\n"
        "kind: feature\n"
        "labels: []\n"
        f"status: {status}\n"
        "priority: P2\n"
        "appetite: 1d\n"
        f"created: {created}\n"
        f"depends_on: {deps}\n"
        f"blocked_by: {blocked}\n"
        f"references: {refs}\n"
        f"{ext}"
        "---\n"
        f"# {task_id}: {title}\n\n"
        f"**Outcome (one sentence):** {outcome}\n\n"
        "## Work Log\n"
    )


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    (root / "docs" / "tasks").mkdir(parents=True)
    return root


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    c = init_db(tmp_path / "test.db")
    yield c
    c.close()


def _write(project: Path, name: str, content: str) -> Path:
    p = project / "docs" / "tasks" / name
    p.write_text(content, encoding="utf-8")
    return p


class TestShimSurface:
    def test_sync_alias_exists_and_is_sync_tasks(self) -> None:
        # background.py calls task_sync.sync(...) — its absence silently
        # broke the background task-sync loop pre-TASK-398.
        assert task_sync.sync is task_sync.sync_tasks

    def test_sync_tasks_returns_board_and_legacy_keys(self, conn, project) -> None:
        _write(project, "TASK-001-a.md", _lean_card("TASK-001", "Alpha"))
        stats = task_sync.sync_tasks(conn, project)
        for key in ("scanned", "upserted", "skipped_unchanged", "parse_errors",
                    "new", "errors", "skipped"):
            assert key in stats
        assert stats["upserted"] == stats["new"] == 1
        assert stats["errors"] == 0


class TestLeanSync:
    def test_status_comes_from_frontmatter(self, conn, project) -> None:
        _write(project, "TASK-001-a.md", _lean_card("TASK-001", "Alpha", status="in_progress"))
        task_sync.sync_tasks(conn, project)
        row = conn.execute("SELECT status FROM tasks WHERE task_id='TASK-001'").fetchone()
        assert row[0] == "in_progress"

    def test_lean_fields_persisted(self, conn, project) -> None:
        _write(
            project,
            "TASK-002-b.md",
            _lean_card(
                "TASK-002",
                "Beta",
                swimlane="docs",
                outcome="Ship the beta docs.",
                blocked_by=("TASK-001",),
                references=("docs/spec.md",),
                external_ref="github#42",
                created="2026-05-30",
            ),
        )
        task_sync.sync_tasks(conn, project)
        row = conn.execute(
            "SELECT domain, goal_text, blocked_by_json, references_json, "
            "external_ref, created_at FROM tasks WHERE task_id='TASK-002'"
        ).fetchone()
        assert row[0] == "DOCS"
        assert row[1] == "Ship the beta docs."
        assert json.loads(row[2]) == ["TASK-001"]
        assert json.loads(row[3]) == ["docs/spec.md"]
        assert row[4] == "github#42"
        assert row[5] == "2026-05-30"

    def test_skip_unchanged_then_force_resyncs(self, conn, project) -> None:
        _write(project, "TASK-003-c.md", _lean_card("TASK-003", "Gamma"))
        task_sync.sync_tasks(conn, project)
        stats = task_sync.sync_tasks(conn, project)
        assert stats["skipped_unchanged"] == 1
        stats = task_sync.sync_tasks(conn, project, force=True)
        assert stats["upserted"] == 1
        assert stats["skipped_unchanged"] == 0


class TestSyncConflict:
    def test_backward_move_recorded_as_conflict(self, conn, project, caplog) -> None:
        path = _write(project, "TASK-004-d.md", _lean_card("TASK-004", "Delta", status="complete"))
        task_sync.sync_tasks(conn, project)
        # Simulate a stale git revert: file content moves the task BACKWARD.
        path.write_text(_lean_card("TASK-004", "Delta", status="in_progress"), encoding="utf-8")
        with caplog.at_level("WARNING"):
            task_sync.sync_tasks(conn, project, force=True)
        reason = conn.execute(
            "SELECT reason FROM task_status_history WHERE task_id='TASK-004' "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()[0]
        assert "sync-conflict" in reason
        assert any("sync conflict" in r.message for r in caplog.records)

    def test_forward_move_is_plain_file_sync(self, conn, project) -> None:
        path = _write(project, "TASK-005-e.md", _lean_card("TASK-005", "Eps", status="icebox"))
        task_sync.sync_tasks(conn, project)
        path.write_text(_lean_card("TASK-005", "Eps", status="testing"), encoding="utf-8")
        task_sync.sync_tasks(conn, project, force=True)
        reason = conn.execute(
            "SELECT reason FROM task_status_history WHERE task_id='TASK-005' "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()[0]
        assert reason == "file-sync"
