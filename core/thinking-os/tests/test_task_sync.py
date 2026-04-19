"""
Tests for core/thinking-os/task_sync.py — Phase C.3.

Covers:
  - parse_task_index (4 status markers, phase headings, missing file)
  - sync_tasks happy path (first run, skip on mtime, re-sync on change, delete orphan)
  - sync_tasks status-only patch (file unchanged, index status changed)
  - sync_status_only fast path
  - Embedding side effect (REQUIRES_RAG)
  - Graceful degradation when embeddings unavailable
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import embeddings  # noqa: E402
from db import init_db  # noqa: E402
from task_sync import (  # noqa: E402
    _canonicalize_task_id,
    parse_task_index,
    sync_status_only,
    sync_tasks,
)

REQUIRES_RAG = pytest.mark.skipif(
    not embeddings.is_available(),
    reason="sentence-transformers + numpy not installed (uv sync --extra rag)",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_db(tmp_path: Path) -> sqlite3.Connection:
    conn = init_db(tmp_path / "test.db")
    yield conn
    conn.close()


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """Build a minimal project with docs/tasks/ and docs/tasks.md."""
    project = tmp_path / "project"
    tasks_dir = project / "docs" / "tasks"
    tasks_dir.mkdir(parents=True)

    # Three real-looking task files with dependencies between them
    (tasks_dir / "TASK-001-foundation.md").write_text(
        "<!-- domain:DOCS | layer:task | ssot:true | updated:2026-04-06 -->\n"
        "# TASK-001: [DOCS] Foundation setup\n\n"
        "## Goal\n\n"
        "Lay the groundwork for the project docs system.\n\n"
        "## Requirements\n\n"
        "1. Given a fresh repo, when init runs, then docs/ is created.\n\n"
        "## Dependencies\n\n- None.\n",
        encoding="utf-8",
    )
    (tasks_dir / "TASK-002-backend-scaffold.md").write_text(
        "<!-- domain:BACKEND | layer:task | ssot:true | updated:2026-04-06 -->\n"
        "# TASK-002: [BACKEND] Backend scaffold\n\n"
        "## Goal\n\n"
        "Stand up the Django backend skeleton.\n\n"
        "## Dependencies\n\n- TASK-001 — foundation must exist first\n",
        encoding="utf-8",
    )
    (tasks_dir / "TASK-003-auth-flow.md").write_text(
        "<!-- domain:BACKEND | layer:task | ssot:true | updated:2026-04-06 -->\n"
        "# TASK-003: [BACKEND] Auth flow\n\n"
        "## Goal\n\n"
        "Implement JWT authentication end to end.\n\n"
        "## Dependencies\n\n- TASK-002 — backend must exist before auth\n",
        encoding="utf-8",
    )

    # Task index with mixed statuses
    (project / "docs" / "tasks.md").write_text(
        "<!-- domain:ALL | layer:index | ssot:true | updated:2026-04-06 -->\n"
        "# Tasks\n\n"
        "## Phase 1\n\n"
        "- [x] TASK-001: [DOCS] Foundation setup\n"
        "- [/] TASK-002: [BACKEND] Backend scaffold\n"
        "- [ ] TASK-003: [BACKEND] Auth flow\n",
        encoding="utf-8",
    )
    return project


# ---------------------------------------------------------------------------
# parse_task_index
# ---------------------------------------------------------------------------

class TestParseTaskIndex:
    def test_parses_done_status(self, tmp_path: Path) -> None:
        index = tmp_path / "tasks.md"
        index.write_text("- [x] TASK-001: Done task\n")
        assert parse_task_index(index) == {"TASK-001": "done"}

    def test_parses_wip_status(self, tmp_path: Path) -> None:
        index = tmp_path / "tasks.md"
        index.write_text("- [/] TASK-042: In progress\n")
        assert parse_task_index(index) == {"TASK-042": "wip"}

    def test_parses_open_status(self, tmp_path: Path) -> None:
        index = tmp_path / "tasks.md"
        index.write_text("- [ ] TASK-100: Open task\n")
        assert parse_task_index(index) == {"TASK-100": "open"}

    def test_parses_blocked_status(self, tmp_path: Path) -> None:
        index = tmp_path / "tasks.md"
        index.write_text("- (BLOCKED: waiting on infra) TASK-050: Blocked task\n")
        assert parse_task_index(index) == {"TASK-050": "blocked"}

    def test_parses_mixed_statuses(self, tmp_path: Path) -> None:
        index = tmp_path / "tasks.md"
        index.write_text(
            "# Tasks\n\n"
            "## Phase 1\n\n"
            "- [x] TASK-001: Done\n"
            "- [/] TASK-002: WIP\n"
            "- [ ] TASK-003: Open\n"
            "- (BLOCKED: no resources) TASK-004: Blocked\n"
        )
        result = parse_task_index(index)
        assert result == {
            "TASK-001": "done",
            "TASK-002": "wip",
            "TASK-003": "open",
            "TASK-004": "blocked",
        }

    def test_ignores_phase_headings(self, tmp_path: Path) -> None:
        """H2 phase headings should not confuse the status parser."""
        index = tmp_path / "tasks.md"
        index.write_text(
            "## Phase 1 — Setup\n\n"
            "- [x] TASK-001: Task\n\n"
            "## Phase 2 — Execution\n\n"
            "- [ ] TASK-002: Task\n"
        )
        result = parse_task_index(index)
        assert len(result) == 2

    def test_missing_index_returns_empty_map(self, tmp_path: Path) -> None:
        assert parse_task_index(tmp_path / "nonexistent.md") == {}

    def test_canonicalizes_task_ids(self, tmp_path: Path) -> None:
        """TASK-3 in source should become TASK-003 in the map."""
        index = tmp_path / "tasks.md"
        index.write_text("- [x] TASK-3: Old style short id\n")
        assert parse_task_index(index) == {"TASK-003": "done"}


# ---------------------------------------------------------------------------
# sync_tasks — happy path
# ---------------------------------------------------------------------------

class TestSyncTasksHappyPath:
    def test_first_run_inserts_all(
        self, tmp_db: sqlite3.Connection, tmp_project: Path
    ) -> None:
        stats = sync_tasks(tmp_db, project_root=tmp_project)
        assert stats["processed"] == 3
        assert stats["new"] == 3
        assert stats["updated"] == 0
        assert stats["skipped"] == 0
        assert stats["deleted"] == 0
        assert stats["errors"] == 0

        # Verify all three rows landed in the DB
        count = tmp_db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        assert count == 3

    def test_status_read_from_tasks_md(
        self, tmp_db: sqlite3.Connection, tmp_project: Path
    ) -> None:
        sync_tasks(tmp_db, project_root=tmp_project)
        statuses = {
            row[0]: row[1]
            for row in tmp_db.execute("SELECT task_id, status FROM tasks").fetchall()
        }
        assert statuses["TASK-001"] == "done"
        assert statuses["TASK-002"] == "wip"
        assert statuses["TASK-003"] == "open"

    def test_domain_extracted(
        self, tmp_db: sqlite3.Connection, tmp_project: Path
    ) -> None:
        sync_tasks(tmp_db, project_root=tmp_project)
        domains = {
            row[0]: row[1]
            for row in tmp_db.execute("SELECT task_id, domain FROM tasks").fetchall()
        }
        assert domains["TASK-001"] == "DOCS"
        assert domains["TASK-002"] == "BACKEND"

    def test_dependencies_stored_as_json(
        self, tmp_db: sqlite3.Connection, tmp_project: Path
    ) -> None:
        sync_tasks(tmp_db, project_root=tmp_project)
        row = tmp_db.execute(
            "SELECT dependencies FROM tasks WHERE task_id = 'TASK-002'"
        ).fetchone()
        deps = json.loads(row[0])
        assert deps == ["TASK-001"]

    def test_second_run_skips_unchanged(
        self, tmp_db: sqlite3.Connection, tmp_project: Path
    ) -> None:
        sync_tasks(tmp_db, project_root=tmp_project)
        second = sync_tasks(tmp_db, project_root=tmp_project)
        assert second["processed"] == 3
        assert second["skipped"] == 3
        assert second["new"] == 0
        assert second["updated"] == 0

    def test_modified_file_re_synced(
        self, tmp_db: sqlite3.Connection, tmp_project: Path
    ) -> None:
        sync_tasks(tmp_db, project_root=tmp_project)

        # Modify TASK-002 goal text
        target = tmp_project / "docs" / "tasks" / "TASK-002-backend-scaffold.md"
        target.write_text(
            "<!-- domain:BACKEND | layer:task | ssot:true | updated:2026-04-07 -->\n"
            "# TASK-002: [BACKEND] Backend scaffold\n\n"
            "## Goal\n\n"
            "Updated goal: now includes Celery worker setup.\n\n"
            "## Dependencies\n\n- TASK-001 — foundation must exist first\n",
            encoding="utf-8",
        )
        # Bump mtime (file system may be second-precision)
        future = int(time.time()) + 120
        os.utime(target, (future, future))

        second = sync_tasks(tmp_db, project_root=tmp_project)
        assert second["updated"] == 1
        assert second["new"] == 0

        # Verify the updated content landed
        row = tmp_db.execute(
            "SELECT goal_text FROM tasks WHERE task_id = 'TASK-002'"
        ).fetchone()
        assert "Celery worker" in row[0]

    def test_deleted_file_removed_from_db(
        self, tmp_db: sqlite3.Connection, tmp_project: Path
    ) -> None:
        sync_tasks(tmp_db, project_root=tmp_project)
        # Delete TASK-003
        (tmp_project / "docs" / "tasks" / "TASK-003-auth-flow.md").unlink()
        second = sync_tasks(tmp_db, project_root=tmp_project)
        assert second["deleted"] == 1
        remaining = {
            row[0]
            for row in tmp_db.execute("SELECT task_id FROM tasks").fetchall()
        }
        assert "TASK-003" not in remaining
        assert "TASK-001" in remaining
        assert "TASK-002" in remaining

    def test_force_resyncs_all(
        self, tmp_db: sqlite3.Connection, tmp_project: Path
    ) -> None:
        sync_tasks(tmp_db, project_root=tmp_project)
        second = sync_tasks(tmp_db, project_root=tmp_project, force=True)
        assert second["skipped"] == 0
        assert second["updated"] == 3

    def test_status_only_patch_when_file_unchanged(
        self, tmp_db: sqlite3.Connection, tmp_project: Path
    ) -> None:
        """If tasks.md status changes but the detail file is unchanged, the
        skipped path should still update the status in-place."""
        sync_tasks(tmp_db, project_root=tmp_project)
        # Change TASK-003 from open to done in the index
        index_path = tmp_project / "docs" / "tasks.md"
        content = index_path.read_text()
        content = content.replace("- [ ] TASK-003:", "- [x] TASK-003:")
        index_path.write_text(content)

        sync_tasks(tmp_db, project_root=tmp_project)
        status = tmp_db.execute(
            "SELECT status FROM tasks WHERE task_id = 'TASK-003'"
        ).fetchone()[0]
        assert status == "done"


# ---------------------------------------------------------------------------
# sync_tasks — edge cases
# ---------------------------------------------------------------------------

class TestSyncTasksEdgeCases:
    def test_missing_tasks_dir_returns_empty_stats(
        self, tmp_db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        project = tmp_path / "empty-project"
        project.mkdir()
        stats = sync_tasks(tmp_db, project_root=project)
        assert stats["processed"] == 0
        assert stats["errors"] == 0

    def test_non_task_file_counted_as_error(
        self, tmp_db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """A README in the tasks directory shouldn't crash — it just fails to parse."""
        project = tmp_path / "project"
        tasks_dir = project / "docs" / "tasks"
        tasks_dir.mkdir(parents=True)
        (tasks_dir / "README.md").write_text(
            "# How to write a task\n\nThis is not a task file.\n"
        )
        (project / "docs" / "tasks.md").write_text("# Tasks\n")
        stats = sync_tasks(tmp_db, project_root=project)
        assert stats["processed"] == 1
        assert stats["errors"] == 1
        assert stats["new"] == 0

    def test_archive_subdirectory_ignored(
        self, tmp_db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        project = tmp_path / "project"
        tasks_dir = project / "docs" / "tasks"
        archive = tasks_dir / "archive"
        archive.mkdir(parents=True)

        (tasks_dir / "TASK-001-active.md").write_text(
            "# TASK-001: Active\n\n## Goal\n\nDo it.\n"
        )
        (archive / "TASK-999-old.md").write_text(
            "# TASK-999: Archived\n\n## Goal\n\nOld.\n"
        )
        (project / "docs" / "tasks.md").write_text(
            "- [ ] TASK-001: Active\n"
        )

        stats = sync_tasks(tmp_db, project_root=project)
        assert stats["new"] == 1
        assert stats["processed"] == 1
        task_ids = {
            row[0] for row in tmp_db.execute("SELECT task_id FROM tasks").fetchall()
        }
        assert "TASK-999" not in task_ids


# ---------------------------------------------------------------------------
# sync_status_only
# ---------------------------------------------------------------------------

class TestSyncStatusOnly:
    def test_updates_changed_statuses(
        self, tmp_db: sqlite3.Connection, tmp_project: Path
    ) -> None:
        sync_tasks(tmp_db, project_root=tmp_project)
        # Change TASK-002 from wip to done
        index_path = tmp_project / "docs" / "tasks.md"
        content = index_path.read_text()
        content = content.replace("- [/] TASK-002:", "- [x] TASK-002:")
        index_path.write_text(content)

        stats = sync_status_only(tmp_db, project_root=tmp_project)
        assert stats["updated"] == 1
        # Plus 2 unchanged
        assert stats["unchanged"] == 2

        status = tmp_db.execute(
            "SELECT status FROM tasks WHERE task_id = 'TASK-002'"
        ).fetchone()[0]
        assert status == "done"

    def test_missing_index_returns_empty_stats(
        self, tmp_db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()
        stats = sync_status_only(tmp_db, project_root=empty)
        assert stats == {"updated": 0, "unchanged": 0}


# ---------------------------------------------------------------------------
# Embeddings integration (requires rag extras)
# ---------------------------------------------------------------------------

class TestSyncEmbeddings:
    @REQUIRES_RAG
    def test_sync_creates_task_embeddings(
        self, tmp_db: sqlite3.Connection, tmp_project: Path
    ) -> None:
        sync_tasks(tmp_db, project_root=tmp_project)
        count = tmp_db.execute(
            "SELECT COUNT(*) FROM embeddings WHERE source_table = 'tasks'"
        ).fetchone()[0]
        # All 3 tasks should have embeddings
        assert count == 3

    def test_sync_succeeds_without_rag_extras(
        self, tmp_db: sqlite3.Connection, tmp_project: Path, monkeypatch
    ) -> None:
        """Mock embeddings unavailability — sync should still succeed."""
        monkeypatch.setattr(embeddings, "is_available", lambda: False)
        stats = sync_tasks(tmp_db, project_root=tmp_project)
        assert stats["new"] == 3
        assert stats["errors"] == 0


# ---------------------------------------------------------------------------
# Canonicalization helper
# ---------------------------------------------------------------------------

class TestCanonicalizeTaskId:
    def test_pads_single_digit(self) -> None:
        assert _canonicalize_task_id("TASK-3") == "TASK-003"

    def test_preserves_three_digit(self) -> None:
        assert _canonicalize_task_id("TASK-199") == "TASK-199"

    def test_preserves_four_digit(self) -> None:
        assert _canonicalize_task_id("TASK-1234") == "TASK-1234"

    def test_invalid_input_unchanged(self) -> None:
        assert _canonicalize_task_id("NOT-A-TASK") == "NOT-A-TASK"


# ---------------------------------------------------------------------------
# Regression: symlinked project root (macOS /tmp vs /private/tmp safety)
# ---------------------------------------------------------------------------

class TestSyncPathResolutionRegression:
    """Guard against the `/tmp` vs `/private/tmp` ValueError that bit
    doc_indexer during Phase B+C end-to-end verification. sync_tasks must
    resolve project_root internally so callers can pass either the
    symlinked or the resolved form.
    """

    def test_symlinked_project_root_accepted(
        self, tmp_db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        project = tmp_path / "project"
        tasks_dir = project / "docs" / "tasks"
        tasks_dir.mkdir(parents=True)
        (tasks_dir / "TASK-001-demo.md").write_text(
            "# TASK-001: [DOCS] Demo task\n\n## Goal\n\nDemo.\n",
            encoding="utf-8",
        )
        (project / "docs" / "tasks.md").write_text(
            "- [ ] TASK-001: [DOCS] Demo task\n", encoding="utf-8",
        )

        # Symlink the project and pass the symlink to sync_tasks — must
        # not raise ValueError when computing relative file paths.
        link_to_project = tmp_path / "link-to-project"
        link_to_project.symlink_to(project, target_is_directory=True)

        stats = sync_tasks(tmp_db, project_root=link_to_project)

        assert stats["errors"] == 0
        assert stats["new"] == 1

        row = tmp_db.execute(
            "SELECT file_path FROM tasks WHERE task_id = 'TASK-001'"
        ).fetchone()
        assert row is not None
        assert not row[0].startswith("/"), f"expected relative path, got {row[0]!r}"
