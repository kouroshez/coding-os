"""
Tests for confidence decay script (TASK-139).

Covers exponential decay formula, effective_decay_rate anti-forgetting,
archive logic, working memory cleanup, and absent DB handling.
"""

from __future__ import annotations

import math
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import init_db
from decay import (
    CONFIDENCE_FLOOR,
    decay_confidence,
    effective_decay_rate,
    run_decay,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    c = init_db(tmp_path / "test.db")
    yield c
    c.close()


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    p = tmp_path / "decay_test.db"
    c = init_db(p)
    c.close()
    return p


# ---------------------------------------------------------------------------
# effective_decay_rate
# ---------------------------------------------------------------------------


class TestEffectiveDecayRate:
    def test_base_rate_passthrough(self) -> None:
        rate = effective_decay_rate(
            base_rate=0.1,
            times_validated=0,
            impact_score=0.5,
            last_accessed_days=30,
        )
        assert rate == 0.1

    def test_deep_encoding_reduces_rate(self) -> None:
        rate = effective_decay_rate(
            base_rate=0.1,
            times_validated=5,
            impact_score=0.5,
            last_accessed_days=30,
        )
        assert rate == pytest.approx(0.03)  # 0.1 * 0.3

    def test_high_impact_reduces_rate(self) -> None:
        rate = effective_decay_rate(
            base_rate=0.1,
            times_validated=0,
            impact_score=0.8,
            last_accessed_days=30,
        )
        assert rate == pytest.approx(0.05)  # 0.1 * 0.5

    def test_deep_and_high_impact_stacks(self) -> None:
        rate = effective_decay_rate(
            base_rate=0.1,
            times_validated=5,
            impact_score=0.8,
            last_accessed_days=30,
        )
        assert rate == pytest.approx(0.015)  # 0.1 * 0.3 * 0.5

    def test_recently_accessed_zero_rate(self) -> None:
        rate = effective_decay_rate(
            base_rate=0.1,
            times_validated=0,
            impact_score=0.5,
            last_accessed_days=3,
        )
        assert rate == 0.0

    def test_never_accessed_uses_base(self) -> None:
        rate = effective_decay_rate(
            base_rate=0.1,
            times_validated=0,
            impact_score=0.5,
            last_accessed_days=None,
        )
        assert rate == 0.1

    def test_exactly_7_days_is_protected(self) -> None:
        rate = effective_decay_rate(
            base_rate=0.1,
            times_validated=0,
            impact_score=0.5,
            last_accessed_days=7,
        )
        assert rate == 0.0

    def test_8_days_not_protected(self) -> None:
        rate = effective_decay_rate(
            base_rate=0.1,
            times_validated=0,
            impact_score=0.5,
            last_accessed_days=8,
        )
        assert rate > 0.0


# ---------------------------------------------------------------------------
# decay_confidence
# ---------------------------------------------------------------------------


class TestDecayConfidence:
    def test_no_decay_at_zero_months(self) -> None:
        result = decay_confidence(confidence=0.7, months_since_validated=0, eff_rate=0.1)
        assert result == 0.7

    def test_no_decay_at_zero_rate(self) -> None:
        result = decay_confidence(confidence=0.7, months_since_validated=6, eff_rate=0.0)
        assert result == 0.7

    def test_one_month_decay(self) -> None:
        result = decay_confidence(confidence=0.7, months_since_validated=1, eff_rate=0.1)
        expected = 0.7 * math.exp(-0.1 * 1)
        assert result == pytest.approx(expected)

    def test_two_month_decay(self) -> None:
        result = decay_confidence(confidence=0.7, months_since_validated=2, eff_rate=0.1)
        expected = 0.7 * math.exp(-0.1 * 2)
        assert result == pytest.approx(expected)

    def test_floor_at_01(self) -> None:
        result = decay_confidence(confidence=0.15, months_since_validated=100, eff_rate=0.1)
        assert result == CONFIDENCE_FLOOR

    def test_high_impact_slow_decay(self) -> None:
        normal = decay_confidence(confidence=0.7, months_since_validated=6, eff_rate=0.1)
        high_impact = decay_confidence(confidence=0.7, months_since_validated=6, eff_rate=0.025)
        assert high_impact > normal

    def test_decay_schedule_12_months(self) -> None:
        """Verify the 12-month decay from spec table."""
        result = decay_confidence(confidence=0.7, months_since_validated=12, eff_rate=0.1)
        # 0.7 * exp(-1.2) ≈ 0.21
        assert 0.19 < result < 0.23


# ---------------------------------------------------------------------------
# run_decay batch
# ---------------------------------------------------------------------------


class TestRunDecay:
    def test_absent_db(self, tmp_path: Path) -> None:
        result = run_decay(tmp_path / "nonexistent.db")
        assert result["status"] == "no_db"

    def test_empty_db(self, db_path: Path) -> None:
        result = run_decay(db_path)
        assert result["total_patterns"] == 0
        assert result["decayed"] == 0

    def test_decays_old_pattern(self, db_path: Path) -> None:
        conn = init_db(db_path)
        try:
            conn.execute(
                "INSERT INTO learned_patterns (pattern, confidence, decay_rate, "
                "last_validated, times_validated, impact_score) "
                "VALUES (?, ?, ?, datetime('now', '-90 days'), ?, ?)",
                ("Old pattern", 0.7, 0.1, 1, 0.5),
            )
            conn.commit()
        finally:
            conn.close()

        result = run_decay(db_path)
        assert result["decayed"] >= 1

        # Verify confidence decreased
        conn = init_db(db_path)
        try:
            row = conn.execute(
                "SELECT confidence FROM learned_patterns WHERE pattern = 'Old pattern'"
            ).fetchone()
            assert row[0] < 0.7
        finally:
            conn.close()

    def test_archives_at_floor(self, db_path: Path) -> None:
        conn = init_db(db_path)
        try:
            conn.execute(
                "INSERT INTO learned_patterns (pattern, confidence, decay_rate, "
                "last_validated, times_validated, impact_score) "
                "VALUES (?, ?, ?, datetime('now', '-365 days'), ?, ?)",
                ("Very old pattern", 0.15, 0.1, 0, 0.5),
            )
            conn.commit()
        finally:
            conn.close()

        result = run_decay(db_path)
        assert result["archived"] >= 1

        conn = init_db(db_path)
        try:
            row = conn.execute(
                "SELECT promoted_to FROM learned_patterns WHERE pattern = 'Very old pattern'"
            ).fetchone()
            assert row[0] == "archived"
        finally:
            conn.close()

    def test_skips_already_archived(self, db_path: Path) -> None:
        conn = init_db(db_path)
        try:
            conn.execute(
                "INSERT INTO learned_patterns (pattern, confidence, promoted_to) VALUES (?, ?, ?)",
                ("Archived pattern", 0.1, "archived"),
            )
            conn.commit()
        finally:
            conn.close()

        result = run_decay(db_path)
        assert result["total_patterns"] == 0  # archived excluded

    def test_protected_pattern_unchanged(self, db_path: Path) -> None:
        conn = init_db(db_path)
        try:
            conn.execute(
                "INSERT INTO learned_patterns (pattern, confidence, decay_rate, "
                "last_validated, last_accessed_at, times_validated, impact_score) "
                "VALUES (?, ?, ?, datetime('now', '-90 days'), datetime('now', '-3 days'), ?, ?)",
                ("Protected pattern", 0.7, 0.1, 10, 0.9),
            )
            conn.commit()
        finally:
            conn.close()

        result = run_decay(db_path)
        assert result["unchanged"] >= 1

    def test_dry_run_no_changes(self, db_path: Path) -> None:
        conn = init_db(db_path)
        try:
            conn.execute(
                "INSERT INTO learned_patterns (pattern, confidence, decay_rate, "
                "last_validated, times_validated, impact_score) "
                "VALUES (?, ?, ?, datetime('now', '-90 days'), ?, ?)",
                ("Dry run test", 0.7, 0.1, 1, 0.5),
            )
            conn.commit()
        finally:
            conn.close()

        run_decay(db_path, dry_run=True)

        conn = init_db(db_path)
        try:
            row = conn.execute(
                "SELECT confidence FROM learned_patterns WHERE pattern = 'Dry run test'"
            ).fetchone()
            assert row[0] == 0.7  # unchanged
        finally:
            conn.close()

    def test_working_memory_cleanup(self, db_path: Path) -> None:
        conn = init_db(db_path)
        try:
            conn.execute(
                "INSERT INTO observations (title, memory_type, expires_at) "
                "VALUES (?, ?, datetime('now', '-1 hour'))",
                ("Expired working memory", "working"),
            )
            conn.execute(
                "INSERT INTO observations (title, memory_type, expires_at) "
                "VALUES (?, ?, datetime('now', '+1 hour'))",
                ("Active working memory", "working"),
            )
            conn.execute(
                "INSERT INTO observations (title, memory_type) VALUES (?, ?)",
                ("Permanent observation", "discovery"),
            )
            conn.commit()
        finally:
            conn.close()

        result = run_decay(db_path)
        assert result["working_memory_cleaned"] == 1

        conn = init_db(db_path)
        try:
            count = conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
            assert count == 2  # active + permanent remain
        finally:
            conn.close()
