"""
Tests for record_outcome.py (TASK-136 re-implementation).

Covers DB write, skip-if-absent, outcome validation, upsert, and domain detection.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import init_db
from record_outcome import _detect_domain, record_outcome


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    p = tmp_path / "test.db"
    c = init_db(p)
    c.close()
    return p


class TestRecordOutcome:
    def test_records_to_db(self, db_path: Path) -> None:
        result = record_outcome(
            task_id="TASK-100",
            task_type="feat",
            outcome="success",
            msg="Test task",
            db_path=db_path,
        )
        assert result["status"] == "recorded"

    def test_data_integrity(self, db_path: Path) -> None:
        record_outcome(
            task_id="TASK-101",
            task_type="fix",
            outcome="rework",
            msg="Backend fix",
            db_path=db_path,
        )
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM task_outcomes WHERE task_id = 'TASK-101'").fetchone()
        conn.close()
        assert row is not None
        assert row["outcome"] == "rework"
        assert row["type"] == "fix"

    def test_skip_if_db_absent(self, tmp_path: Path) -> None:
        result = record_outcome(
            task_id="TASK-102",
            task_type="feat",
            outcome="success",
            db_path=tmp_path / "nonexistent.db",
        )
        assert result["status"] == "skipped"

    def test_invalid_outcome(self, db_path: Path) -> None:
        result = record_outcome(
            task_id="TASK-103",
            task_type="feat",
            outcome="invalid",
            db_path=db_path,
        )
        assert result["status"] == "error"

    def test_upsert_updates_existing(self, db_path: Path) -> None:
        record_outcome(
            task_id="TASK-104",
            task_type="feat",
            outcome="partial",
            db_path=db_path,
        )
        record_outcome(
            task_id="TASK-104",
            task_type="feat",
            outcome="success",
            db_path=db_path,
        )
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM task_outcomes WHERE task_id = 'TASK-104'").fetchone()
        conn.close()
        assert row["outcome"] == "success"
        # Should only have 1 row
        conn = sqlite3.connect(str(db_path))
        count = conn.execute(
            "SELECT COUNT(*) FROM task_outcomes WHERE task_id = 'TASK-104'"
        ).fetchone()[0]
        conn.close()
        assert count == 1

    def test_all_valid_outcomes(self, db_path: Path) -> None:
        for outcome in ["success", "rework", "partial", "blocked"]:
            result = record_outcome(
                task_id=f"TASK-{outcome}",
                task_type="feat",
                outcome=outcome,
                db_path=db_path,
            )
            assert result["status"] == "recorded"


class TestDetectDomain:
    def test_backend(self) -> None:
        assert _detect_domain("TASK-100", "Django model fix") == "BACKEND"

    def test_frontend(self) -> None:
        assert _detect_domain("TASK-101", "React component update") == "FRONTEND"

    def test_docs(self) -> None:
        assert _detect_domain("TASK-102", "Update docs formatting") == "DOCS"

    def test_infra_default(self) -> None:
        assert _detect_domain("TASK-103", "Build system change") == "INFRA"
