"""
Tests for thinking_os dashboard (TASK-149).

Covers each section, empty DB, absent DB, and data-filled scenarios.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db import init_db
from dashboard import generate_dashboard


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    p = tmp_path / "test.db"
    c = init_db(p)
    c.close()
    return p


@pytest.fixture
def seeded_path(db_path: Path) -> Path:
    conn = init_db(db_path)
    try:
        # Task outcomes
        for i in range(10):
            conn.execute(
                "INSERT INTO task_outcomes (task_id, type, domain, complexity, outcome, model) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (f"TASK-{i}", "feat", ["BACKEND", "FRONTEND"][i % 2],
                 "CLEAR", ["success", "success", "rework"][i % 3],
                 ["sonnet", "opus"][i % 2]),
            )
        # Patterns
        for i in range(8):
            conn.execute(
                "INSERT INTO learned_patterns (pattern, confidence, domain) VALUES (?, ?, ?)",
                (f"Pattern {i}", 0.1 + i * 0.1, "BACKEND"),
            )
        # Observations
        for i in range(5):
            conn.execute(
                "INSERT INTO observations (title, memory_type) VALUES (?, ?)",
                (f"Obs {i}", "discovery"),
            )
        # Experiments
        conn.execute(
            "INSERT INTO experiment_log (task_id, hypothesis, outcome) VALUES (?, ?, ?)",
            ("TASK-5", "Test hypothesis", "pass"),
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


class TestDashboard:
    def test_absent_db(self, tmp_path: Path) -> None:
        output = generate_dashboard(tmp_path / "nonexistent.db")
        assert "No DB Found" in output
        assert "No thinking_os.db found" in output

    def test_empty_db(self, db_path: Path) -> None:
        output = generate_dashboard(db_path)
        assert "Dashboard" in output
        assert "Patterns       : 0" in output
        assert "Observations   : 0" in output

    def test_overview_section(self, seeded_path: Path) -> None:
        output = generate_dashboard(seeded_path)
        assert "Overview" in output
        assert "Schema version" in output
        assert "FTS5 available" in output

    def test_confidence_distribution(self, seeded_path: Path) -> None:
        output = generate_dashboard(seeded_path)
        assert "Confidence Distribution" in output
        assert "archived" in output
        assert "strong" in output

    def test_model_success_rates(self, seeded_path: Path) -> None:
        output = generate_dashboard(seeded_path)
        assert "Model Success Rates" in output
        assert "sonnet" in output or "opus" in output

    def test_domain_hotspots(self, seeded_path: Path) -> None:
        output = generate_dashboard(seeded_path)
        assert "Domain Failure Hotspots" in output
        assert "BACKEND" in output or "FRONTEND" in output

    def test_experiments_section(self, seeded_path: Path) -> None:
        output = generate_dashboard(seeded_path)
        assert "Recent Experiments" in output
        assert "Test hypothesis" in output

    def test_no_crash_on_empty_sections(self, db_path: Path) -> None:
        output = generate_dashboard(db_path)
        assert "(no data)" in output or "(no experiments)" in output

    def test_counts_correct(self, seeded_path: Path) -> None:
        output = generate_dashboard(seeded_path)
        assert "Patterns       : 8" in output
        assert "Observations   : 5" in output
        assert "Task outcomes  : 10" in output
