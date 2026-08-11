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
# Regression — fresh pattern must survive the first decay run (audit N1 / 1a)
# ---------------------------------------------------------------------------


class TestFreshPatternSurvivesFirstDecay:
    def test_fresh_pattern_not_archived_on_first_decay(self, db_path: Path) -> None:
        from tools.learning import _upsert_pattern

        c = init_db(db_path)
        res = _upsert_pattern(
            c,
            pattern="fresh mined pattern that must survive the first decay run",
            memory_type="pattern",
            domain="TEST",
            source="learn_extract",
            confidence=0.5,
            concepts="",
        )
        c.commit()
        c.close()
        pid = res["id"]
        assert pid is not None

        run_decay(db_path)

        c2 = init_db(db_path)
        row = c2.execute(
            "SELECT confidence, promoted_to FROM learned_patterns WHERE id = ?",
            (pid,),
        ).fetchone()
        c2.close()
        assert row is not None
        # last_validated stamped at INSERT → age 0 → not aged to 999d → not archived.
        assert row[1] is None, "fresh pattern was archived on its first decay run"
        assert row[0] == pytest.approx(0.5, abs=0.05)


class TestTrustTierDecaySafety:
    """A locked/core pattern is immutable via the protect triggers (RAISE ABORT).
    Decay must exclude those tiers, or one UPDATE raises, unwinds before commit,
    and silently rolls back the ENTIRE run."""

    @staticmethod
    def _insert(c: sqlite3.Connection, pattern: str, conf: float, tier: str) -> None:
        c.execute(
            "INSERT INTO learned_patterns (pattern, memory_type, confidence, decay_rate, "
            "impact_score, times_seen, trust_tier, provenance, last_validated, last_accessed_at) "
            "VALUES (?, 'pattern', ?, 0.1, 0.5, 0, ?, 'x', "
            "datetime('now','-400 days'), datetime('now','-400 days'))",
            (pattern, conf, tier),
        )

    def test_locked_pattern_does_not_abort_decay(self, db_path: Path) -> None:
        c = init_db(db_path)
        self._insert(c, "locked rule", 0.9, "locked")  # would decay → protect trigger aborts
        self._insert(c, "old volatile", 0.5, "volatile")  # must decay → proves run completed
        c.commit()
        c.close()

        run_decay(db_path)  # pre-fix: raises IntegrityError from the locked-row UPDATE

        c2 = init_db(db_path)
        locked = c2.execute(
            "SELECT confidence, promoted_to FROM learned_patterns WHERE pattern='locked rule'"
        ).fetchone()
        volatile = c2.execute(
            "SELECT confidence FROM learned_patterns WHERE pattern='old volatile'"
        ).fetchone()
        c2.close()
        assert locked[0] == 0.9 and locked[1] is None, "locked pattern mutated or run aborted"
        assert volatile[0] < 0.5, "old volatile did not decay → run rolled back by locked-row abort"


class TestEffectiveDecayRate:
    def test_base_rate_passthrough(self) -> None:
        rate = effective_decay_rate(
            base_rate=0.1,
            times_seen=0,
            impact_score=0.5,
            last_accessed_days=30,
        )
        assert rate == 0.1

    def test_deep_encoding_reduces_rate(self) -> None:
        rate = effective_decay_rate(
            base_rate=0.1,
            times_seen=5,
            impact_score=0.5,
            last_accessed_days=30,
        )
        assert rate == pytest.approx(0.03)  # 0.1 * 0.3

    def test_high_impact_reduces_rate(self) -> None:
        rate = effective_decay_rate(
            base_rate=0.1,
            times_seen=0,
            impact_score=0.8,
            last_accessed_days=30,
        )
        assert rate == pytest.approx(0.05)  # 0.1 * 0.5

    def test_deep_and_high_impact_stacks(self) -> None:
        rate = effective_decay_rate(
            base_rate=0.1,
            times_seen=5,
            impact_score=0.8,
            last_accessed_days=30,
        )
        assert rate == pytest.approx(0.015)  # 0.1 * 0.3 * 0.5

    def test_recently_accessed_zero_rate(self) -> None:
        rate = effective_decay_rate(
            base_rate=0.1,
            times_seen=0,
            impact_score=0.5,
            last_accessed_days=3,
        )
        assert rate == 0.0

    def test_never_accessed_uses_base(self) -> None:
        rate = effective_decay_rate(
            base_rate=0.1,
            times_seen=0,
            impact_score=0.5,
            last_accessed_days=None,
        )
        assert rate == 0.1

    def test_exactly_7_days_is_protected(self) -> None:
        rate = effective_decay_rate(
            base_rate=0.1,
            times_seen=0,
            impact_score=0.5,
            last_accessed_days=7,
        )
        assert rate == 0.0

    def test_8_days_not_protected(self) -> None:
        rate = effective_decay_rate(
            base_rate=0.1,
            times_seen=0,
            impact_score=0.5,
            last_accessed_days=8,
        )
        assert rate > 0.0


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
