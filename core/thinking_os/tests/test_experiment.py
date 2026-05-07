"""
Tests for record_experiment.py (TASK-140).

Covers DB write, skip-if-absent, empty hypothesis, and data integrity.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import init_db
from record_experiment import record_experiment


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    p = tmp_path / "test.db"
    c = init_db(p)
    c.close()
    return p


class TestRecordExperiment:
    def test_records_to_db(self, db_path: Path) -> None:
        result = record_experiment(
            task_id="TASK-100",
            hypothesis="Service layer reduces rework",
            test_description="Compare rework rates before/after",
            outcome="pass",
            learning="Services reduced rework by 40%",
            db_path=db_path,
        )
        assert result["status"] == "recorded"
        assert "id" in result

    def test_data_integrity(self, db_path: Path) -> None:
        record_experiment(
            task_id="TASK-101",
            hypothesis="FTS5 faster than LIKE",
            outcome="pass",
            db_path=db_path,
        )
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM experiment_log WHERE task_id = 'TASK-101'"
        ).fetchone()
        conn.close()
        assert row is not None
        assert row["hypothesis"] == "FTS5 faster than LIKE"
        assert row["outcome"] == "pass"

    def test_optional_fields_null(self, db_path: Path) -> None:
        result = record_experiment(
            task_id="TASK-102",
            hypothesis="Minimal experiment",
            db_path=db_path,
        )
        assert result["status"] == "recorded"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM experiment_log WHERE task_id = 'TASK-102'"
        ).fetchone()
        conn.close()
        assert row["test_description"] is None
        assert row["outcome"] is None
        assert row["learning"] is None

    def test_skip_if_db_absent(self, tmp_path: Path) -> None:
        result = record_experiment(
            task_id="TASK-103",
            hypothesis="Should skip",
            db_path=tmp_path / "nonexistent.db",
        )
        assert result["status"] == "skipped"
        assert result["reason"] == "db_absent"

    def test_empty_hypothesis_rejected(self, db_path: Path) -> None:
        result = record_experiment(
            task_id="TASK-104",
            hypothesis="   ",
            db_path=db_path,
        )
        assert result["status"] == "error"

    def test_multiple_experiments_per_task(self, db_path: Path) -> None:
        for i in range(3):
            record_experiment(
                task_id="TASK-105",
                hypothesis=f"Experiment {i}",
                db_path=db_path,
            )
        conn = sqlite3.connect(str(db_path))
        count = conn.execute(
            "SELECT COUNT(*) FROM experiment_log WHERE task_id = 'TASK-105'"
        ).fetchone()[0]
        conn.close()
        assert count == 3
