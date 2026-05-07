"""
Tests for record_review.py (TASK-137 re-implementation).

Covers DB write path, fallback file path, missing DB, directory creation.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import init_db
from record_review import record_review


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    p = tmp_path / "test.db"
    c = init_db(p)
    c.close()
    return p


class TestRecordReviewDB:
    def test_writes_to_db(self, db_path: Path) -> None:
        result = record_review(
            task_id="TASK-100",
            request="Fix login bug",
            investigated="Auth module, session handling",
            learned="Session tokens had wrong TTL",
            completed="Fixed TTL in config",
            next_steps="Monitor error rates",
            db_path=db_path,
        )
        assert result["status"] == "recorded"
        assert result["target"] == "db"
        assert "id" in result

    def test_data_integrity(self, db_path: Path) -> None:
        record_review(
            task_id="TASK-101",
            request="Add search",
            learned="FTS5 is fast",
            db_path=db_path,
        )
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM session_summaries WHERE task_id = 'TASK-101'"
        ).fetchone()
        conn.close()
        assert row is not None
        assert row["request"] == "Add search"
        assert row["learned"] == "FTS5 is fast"

    def test_empty_fields_accepted(self, db_path: Path) -> None:
        result = record_review(task_id="TASK-102", db_path=db_path)
        assert result["status"] == "recorded"

    def test_multiple_reviews_per_task(self, db_path: Path) -> None:
        record_review(task_id="TASK-103", request="First attempt", db_path=db_path)
        record_review(task_id="TASK-103", request="After rework", db_path=db_path)
        conn = sqlite3.connect(str(db_path))
        count = conn.execute(
            "SELECT COUNT(*) FROM session_summaries WHERE task_id = 'TASK-103'"
        ).fetchone()[0]
        conn.close()
        assert count == 2


class TestRecordReviewFallback:
    def test_writes_file_when_db_absent(self, tmp_path: Path) -> None:
        learnings = tmp_path / "learnings"
        result = record_review(
            task_id="TASK-200",
            request="Test fallback",
            learned="Fallback works",
            db_path=tmp_path / "nonexistent.db",
            learnings_dir=learnings,
        )
        assert result["status"] == "recorded"
        assert result["target"] == "file"
        assert (learnings / "TASK-200-review.md").exists()

    def test_fallback_file_content(self, tmp_path: Path) -> None:
        learnings = tmp_path / "learnings"
        record_review(
            task_id="TASK-201",
            request="Content test",
            learned="File format correct",
            db_path=tmp_path / "nonexistent.db",
            learnings_dir=learnings,
        )
        content = (learnings / "TASK-201-review.md").read_text()
        assert "task_id: TASK-201" in content
        assert "## Request" in content
        assert "Content test" in content
        assert "## Learned" in content
        assert "File format correct" in content

    def test_creates_directory_if_missing(self, tmp_path: Path) -> None:
        learnings = tmp_path / "deep" / "nested" / "learnings"
        assert not learnings.exists()
        record_review(
            task_id="TASK-202",
            request="Dir test",
            db_path=tmp_path / "nonexistent.db",
            learnings_dir=learnings,
        )
        assert learnings.exists()
        assert (learnings / "TASK-202-review.md").exists()

    def test_fallback_has_frontmatter(self, tmp_path: Path) -> None:
        learnings = tmp_path / "learnings"
        record_review(
            task_id="TASK-203",
            db_path=tmp_path / "nonexistent.db",
            learnings_dir=learnings,
        )
        content = (learnings / "TASK-203-review.md").read_text()
        assert content.startswith("---\n")
        assert "date:" in content

    def test_empty_fields_show_not_recorded(self, tmp_path: Path) -> None:
        learnings = tmp_path / "learnings"
        record_review(
            task_id="TASK-204",
            db_path=tmp_path / "nonexistent.db",
            learnings_dir=learnings,
        )
        content = (learnings / "TASK-204-review.md").read_text()
        assert "(not recorded)" in content
