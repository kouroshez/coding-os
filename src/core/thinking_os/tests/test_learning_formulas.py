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
    learn_extract,
    penalize_failure,
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


class TestConfidenceFormulas:
    def test_boost_success_increases(self) -> None:
        assert boost_success(0.5) > 0.5

    def test_boost_success_diminishing_returns(self) -> None:
        delta_low = boost_success(0.3) - 0.3
        delta_high = boost_success(0.8) - 0.8
        assert delta_low > delta_high

    def test_boost_success_capped_at_095(self) -> None:
        assert boost_success(0.95) <= 0.95

    def test_penalize_failure_decreases(self) -> None:
        assert penalize_failure(0.5) < 0.5

    def test_penalize_failure_floor_01(self) -> None:
        result = penalize_failure(0.1)
        assert result >= 0.1

    def test_penalize_failure_proportional(self) -> None:
        delta_low = 0.3 - penalize_failure(0.3)
        delta_high = 0.8 - penalize_failure(0.8)
        assert delta_high > delta_low


class TestHumanizeAndTier:
    """Lessons must read for a novice (XAI: speak the user's language); tiers
    replace bare percentages. Contract: learning-extraction.md."""

    def test_humanize_translates_jargon(self) -> None:
        from tools._learning_mining import _humanize_signature

        out = _humanize_signature(
            "predicates_unsatisfied: no EvidenceBundle for predicates ['coverage_100']"
        )
        assert "predicates_unsatisfied" not in out
        assert "proof" in out.lower()

    def test_humanize_passthrough_plain_text(self) -> None:
        from tools._learning_mining import _humanize_signature

        assert _humanize_signature("plain readable message") == "plain readable message"

    def test_pattern_tier_thresholds(self) -> None:
        from tools.learning import pattern_tier

        assert pattern_tier(0.8, 5) == "Trusted"
        assert pattern_tier(0.3, 2) == "Fading"
        assert pattern_tier(0.6, 1) == "Forming"
        assert pattern_tier(0.9, 1) == "Forming"  # high conf, not yet confirmed → not Trusted


class TestStatVarianceGate:
    """Success-rate stats are tautologies on a monotone-success corpus; they are
    minted only when task_outcomes has a non-success outcome to contrast against."""

    @staticmethod
    def _seed(conn, outcomes):
        for i, (dom, outcome) in enumerate(outcomes):
            conn.execute(
                "INSERT INTO task_outcomes (task_id, type, domain, complexity, outcome, skills_used) "
                "VALUES (?, 'feat', ?, 'CLEAR', ?, 'clean-code')",
                (f"TASK-9{i:02d}", dom, outcome),
            )
        conn.commit()

    def _stat_count(self, conn) -> int:
        return conn.execute(
            "SELECT COUNT(*) FROM learned_patterns WHERE memory_type='stat'"
        ).fetchone()[0]

    def test_monotone_success_mints_no_stats(self, conn: sqlite3.Connection) -> None:
        self._seed(conn, [("INFRA", "success")] * 5)
        learn_extract(conn, min_occurrences=3)
        assert self._stat_count(conn) == 0  # every "100%" stat is a tautology → skipped

    def test_variance_mints_stats(self, conn: sqlite3.Connection) -> None:
        self._seed(conn, [("INFRA", "success")] * 5 + [("INFRA", "rework")] * 2)
        learn_extract(conn, min_occurrences=3)
        assert self._stat_count(conn) >= 1  # a non-success outcome makes the rate informative


class TestNarrativeQualityBar:
    """A narrative is only stored if its key_insight is specific — blocks the
    'be careful' slop the Stop nudge could otherwise elicit (the C path)."""

    def test_rejects_generic_insight(self, conn: sqlite3.Connection) -> None:
        from tools._learning_narrative import learn_narrative

        r = learn_narrative(conn, task_id="TASK-1", key_insight="be careful")
        assert "error" in r

    def test_rejects_too_short_insight(self, conn: sqlite3.Connection) -> None:
        from tools._learning_narrative import learn_narrative

        r = learn_narrative(conn, task_id="TASK-1", key_insight="fix it")
        assert "error" in r

    def test_accepts_specific_insight(self, conn: sqlite3.Connection) -> None:
        from tools._learning_narrative import learn_narrative

        r = learn_narrative(
            conn,
            task_id="TASK-1",
            key_insight="FTS5 external-content tables corrupt on rebuild; use own-content tables instead.",
        )
        assert "error" not in r
        assert r.get("status") == "narrative_recorded"
        # The fresh breakthrough pattern must carry last_validated/last_accessed_at
        # so decay reads age 0 (not 999) and does not archive it on the first run.
        row = conn.execute(
            "SELECT last_validated, last_accessed_at FROM learned_patterns WHERE id = ?",
            (r["pattern_id"],),
        ).fetchone()
        assert row[0] is not None and row[1] is not None


class TestStatClassification:
    """Success correlations are STATS, not beliefs. They must be minted with
    memory_type='stat' (excluded from digest + suggest), while failure signals
    (rework) stay beliefs. Re-mining reclassifies legacy 'pattern' baselines."""

    def test_success_baselines_are_stat(self, conn: sqlite3.Connection) -> None:
        for i in range(3):
            conn.execute(
                "INSERT INTO task_outcomes (task_id, type, domain, complexity, outcome, skills_used) "
                "VALUES (?, 'feat', 'INFRA', 'CLEAR', 'success', 'graph-explorer')",
                (f"TASK-S{i}",),
            )
        # one non-success outcome → corpus has variance, so the success-baseline
        # stat is informative and gets minted (variance gate).
        conn.execute(
            "INSERT INTO task_outcomes (task_id, type, domain, complexity, outcome, skills_used) "
            "VALUES ('TASK-RW', 'fix', 'OTHER', 'CLEAR', 'rework', 'clean-code')"
        )
        conn.commit()
        learn_extract(conn, min_occurrences=3)
        rows = conn.execute(
            "SELECT memory_type FROM learned_patterns "
            "WHERE pattern LIKE '%succeeds at%' OR pattern LIKE '%correlates with success%'"
        ).fetchall()
        assert rows
        assert all(r["memory_type"] == "stat" for r in rows)

    def test_rework_pattern_stays_belief(self, seeded_conn: sqlite3.Connection) -> None:
        learn_extract(seeded_conn, min_occurrences=3)
        rows = seeded_conn.execute(
            "SELECT memory_type FROM learned_patterns WHERE pattern LIKE '%rework rate%'"
        ).fetchall()
        assert rows  # BACKEND has 3 reworks in the seeded corpus
        assert all(r["memory_type"] != "stat" for r in rows)

    def test_remine_reclassifies_legacy_pattern_to_stat(
        self, seeded_conn: sqlite3.Connection
    ) -> None:
        from tools._learning_store import _upsert_pattern

        # legacy garbage row minted (pre-fix) as a generic 'pattern'
        seeded_conn.execute(
            "INSERT INTO learned_patterns (pattern, memory_type, domain, source, confidence) "
            "VALUES ('INFRA domain succeeds at 100% (40/40 tasks) — reliable baseline', "
            "'pattern', 'INFRA', 'learn_extract', 0.8)"
        )
        seeded_conn.commit()
        _upsert_pattern(
            seeded_conn,
            pattern="INFRA domain succeeds at 100% (83/83 tasks) — reliable baseline",
            memory_type="stat",
            domain="INFRA",
            source="learn_extract",
            confidence=0.85,
            concepts="[]",
        )
        rows = seeded_conn.execute(
            "SELECT memory_type FROM learned_patterns WHERE domain='INFRA'"
        ).fetchall()
        assert len(rows) == 1  # still one row (count-agnostic identity)
        assert rows[0]["memory_type"] == "stat"  # reclassified on re-mine
