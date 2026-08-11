"""
Tests for MCP learning tools (TASK-144).

Covers extract (pattern detection, min_occurrences, insufficient data),
suggest (spaced repetition, domain filter), and validate (confidence formulas).
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import init_db
from tools.learning import (
    boost_success,
    learn_validate,
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
def seeded_conn(conn: sqlite3.Connection) -> sqlite3.Connection:
    """DB with enough task outcomes to trigger pattern extraction."""
    outcomes = [
        ("TASK-100", "feat", "BACKEND", "CLEAR", "success", "python-django"),
        ("TASK-101", "feat", "BACKEND", "COMPLICATED", "rework", "python-django"),
        ("TASK-102", "fix", "BACKEND", "CLEAR", "rework", "python-django"),
        ("TASK-103", "feat", "BACKEND", "COMPLICATED", "rework", "python-django"),
        ("TASK-104", "feat", "BACKEND", "CLEAR", "success", "python-django"),
        ("TASK-105", "feat", "FRONTEND", "CLEAR", "success", "nextjs-react"),
        ("TASK-106", "feat", "FRONTEND", "CLEAR", "success", "nextjs-react"),
        ("TASK-107", "fix", "FRONTEND", "COMPLICATED", "rework", "nextjs-react"),
    ]
    for task_id, typ, domain, comp, outcome, skills in outcomes:
        conn.execute(
            "INSERT INTO task_outcomes (task_id, type, domain, complexity, outcome, skills_used) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (task_id, typ, domain, comp, outcome, skills),
        )
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# Confidence formulas
# ---------------------------------------------------------------------------


import embeddings

REQUIRES_RAG = pytest.mark.skipif(
    not embeddings.is_available(),
    reason="sentence-transformers + numpy not installed (uv sync --extra rag)",
)


class TestLearnValidate:
    def test_not_found(self, conn: sqlite3.Connection) -> None:
        result = learn_validate(conn, pattern_id=999, was_helpful=True)
        assert "error" in result

    def test_helpful_boosts_confidence(self, seeded_conn: sqlite3.Connection) -> None:
        seeded_conn.execute(
            "INSERT INTO learned_patterns (pattern, confidence) VALUES (?, ?)",
            ("Test pattern", 0.5),
        )
        seeded_conn.commit()
        pid = seeded_conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        result = learn_validate(seeded_conn, pattern_id=pid, was_helpful=True)
        assert result["new_confidence"] > result["old_confidence"]
        assert result["status"] == "validated"

    def test_not_helpful_penalizes(self, seeded_conn: sqlite3.Connection) -> None:
        seeded_conn.execute(
            "INSERT INTO learned_patterns (pattern, confidence) VALUES (?, ?)",
            ("Test pattern 2", 0.6),
        )
        seeded_conn.commit()
        pid = seeded_conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        result = learn_validate(seeded_conn, pattern_id=pid, was_helpful=False)
        assert result["new_confidence"] < result["old_confidence"]
        assert result["status"] == "penalized"

    def test_increments_times_validated(self, seeded_conn: sqlite3.Connection) -> None:
        seeded_conn.execute(
            "INSERT INTO learned_patterns (pattern, confidence, times_validated) VALUES (?, ?, ?)",
            ("Validated pattern", 0.5, 3),
        )
        seeded_conn.commit()
        pid = seeded_conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        learn_validate(seeded_conn, pattern_id=pid, was_helpful=True)
        row = seeded_conn.execute(
            "SELECT times_validated FROM learned_patterns WHERE id = ?", (pid,)
        ).fetchone()
        assert row[0] == 4

    def test_increments_times_violated(self, seeded_conn: sqlite3.Connection) -> None:
        seeded_conn.execute(
            "INSERT INTO learned_patterns (pattern, confidence, times_violated) VALUES (?, ?, ?)",
            ("Violated pattern", 0.5, 1),
        )
        seeded_conn.commit()
        pid = seeded_conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        learn_validate(seeded_conn, pattern_id=pid, was_helpful=False)
        row = seeded_conn.execute(
            "SELECT times_violated FROM learned_patterns WHERE id = ?", (pid,)
        ).fetchone()
        assert row[0] == 2

    def test_confidence_never_below_floor(self, seeded_conn: sqlite3.Connection) -> None:
        seeded_conn.execute(
            "INSERT INTO learned_patterns (pattern, confidence) VALUES (?, ?)",
            ("Low confidence", 0.11),
        )
        seeded_conn.commit()
        pid = seeded_conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        # Penalize multiple times
        for _ in range(10):
            learn_validate(seeded_conn, pattern_id=pid, was_helpful=False)
        row = seeded_conn.execute(
            "SELECT confidence FROM learned_patterns WHERE id = ?", (pid,)
        ).fetchone()
        assert row[0] >= 0.1

    def test_temporal_proximity_bonus(
        self,
        seeded_conn: sqlite3.Connection,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Temporal bonus still works when two validations come from different
        sessions — intra-session repeats are throttled by G.4."""
        seeded_conn.execute(
            "INSERT INTO learned_patterns (pattern, confidence, last_validated) "
            "VALUES (?, ?, CURRENT_TIMESTAMP)",
            ("Temporal test", 0.5),
        )
        seeded_conn.commit()
        pid = seeded_conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Two distinct sessions so throttle doesn't block the second call.
        sessions = iter(["ses-temporal-A", "ses-temporal-B"])
        monkeypatch.setattr(
            "tools._learning_validate._read_session_id_for_validate",
            lambda: next(sessions),
        )

        result1 = learn_validate(seeded_conn, pattern_id=pid, was_helpful=True)
        result2 = learn_validate(seeded_conn, pattern_id=pid, was_helpful=True)
        normal_boost = boost_success(result1["new_confidence"]) - result1["new_confidence"]
        actual_boost = result2["new_confidence"] - result1["new_confidence"]
        assert actual_boost >= normal_boost


class TestLearnValidateThrottle:
    @pytest.fixture
    def pattern_id(self, seeded_conn: sqlite3.Connection) -> int:
        seeded_conn.execute(
            "INSERT INTO learned_patterns (pattern, confidence) VALUES (?, ?)",
            ("Throttle target", 0.5),
        )
        seeded_conn.commit()
        return seeded_conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    def test_second_positive_same_session_is_throttled(
        self,
        seeded_conn: sqlite3.Connection,
        pattern_id: int,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            "tools._learning_validate._read_session_id_for_validate",
            lambda: "ses-throttle-X",
        )
        first = learn_validate(seeded_conn, pattern_id=pattern_id, was_helpful=True)
        assert first["status"] == "validated"
        boosted = first["new_confidence"]

        second = learn_validate(seeded_conn, pattern_id=pattern_id, was_helpful=True)
        assert second["status"] == "throttled"
        # Confidence must NOT change on throttled call
        assert second["new_confidence"] == round(boosted, 4)
        assert second["old_confidence"] == round(boosted, 4)
        assert "reason" in second

    def test_different_session_not_throttled(
        self,
        seeded_conn: sqlite3.Connection,
        pattern_id: int,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        sessions = iter(["ses-A", "ses-B"])
        monkeypatch.setattr(
            "tools._learning_validate._read_session_id_for_validate",
            lambda: next(sessions),
        )
        first = learn_validate(seeded_conn, pattern_id=pattern_id, was_helpful=True)
        second = learn_validate(seeded_conn, pattern_id=pattern_id, was_helpful=True)
        assert first["status"] == "validated"
        assert second["status"] == "validated"
        assert second["new_confidence"] > first["old_confidence"]

    def test_negative_validation_never_throttled(
        self,
        seeded_conn: sqlite3.Connection,
        pattern_id: int,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Violations must always be recorded — agent must be able to flag
        bad patterns even mid-session."""
        monkeypatch.setattr(
            "tools._learning_validate._read_session_id_for_validate",
            lambda: "ses-neg",
        )
        r1 = learn_validate(seeded_conn, pattern_id=pattern_id, was_helpful=False)
        r2 = learn_validate(seeded_conn, pattern_id=pattern_id, was_helpful=False)
        r3 = learn_validate(seeded_conn, pattern_id=pattern_id, was_helpful=False)
        assert r1["status"] == "penalized"
        assert r2["status"] == "penalized"
        assert r3["status"] == "penalized"
        # confidence decreases each time (never throttled)
        assert r3["new_confidence"] < r1["old_confidence"]

    def test_logs_to_pattern_validations(
        self,
        seeded_conn: sqlite3.Connection,
        pattern_id: int,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            "tools._learning_validate._read_session_id_for_validate",
            lambda: "ses-log-test",
        )
        learn_validate(seeded_conn, pattern_id=pattern_id, was_helpful=True)
        learn_validate(seeded_conn, pattern_id=pattern_id, was_helpful=True)  # throttled

        rows = seeded_conn.execute(
            "SELECT session_id, was_helpful, was_throttled "
            "FROM pattern_validations WHERE pattern_id = ? ORDER BY id",
            (pattern_id,),
        ).fetchall()
        assert len(rows) == 2
        assert rows[0]["session_id"] == "ses-log-test"
        assert rows[0]["was_helpful"] == 1
        assert rows[0]["was_throttled"] == 0
        assert rows[1]["was_helpful"] == 1
        assert rows[1]["was_throttled"] == 1  # second call was throttled

    def test_locked_pattern_blocked_before_throttle(
        self,
        seeded_conn: sqlite3.Connection,
    ) -> None:
        """Locked trust_tier short-circuits with a validation error, NEVER
        reaches throttle/DB-trigger — agent gets a clean signal."""
        seeded_conn.execute(
            "INSERT INTO learned_patterns (pattern, confidence, trust_tier) VALUES (?, ?, ?)",
            ("locked rule", 0.8, "locked"),
        )
        seeded_conn.commit()
        pid = seeded_conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        result = learn_validate(seeded_conn, pattern_id=pid, was_helpful=True)
        assert "error" in result
        assert "immutable" in result["error"].lower()
        assert result["trust_tier"] == "locked"

    def test_core_pattern_blocked_before_throttle(
        self,
        seeded_conn: sqlite3.Connection,
    ) -> None:
        seeded_conn.execute(
            "INSERT INTO learned_patterns (pattern, confidence, trust_tier) VALUES (?, ?, ?)",
            ("core rule", 0.9, "core"),
        )
        seeded_conn.commit()
        pid = seeded_conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        result = learn_validate(seeded_conn, pattern_id=pid, was_helpful=False)
        assert "error" in result
        assert result["trust_tier"] == "core"
