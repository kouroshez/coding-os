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
    learn_suggest,
    learn_validate,
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


# ---------------------------------------------------------------------------
# cos_learn_extract
# ---------------------------------------------------------------------------


class TestLearnExtract:
    def test_insufficient_data(self, conn: sqlite3.Connection) -> None:
        result = learn_extract(conn, min_occurrences=3)
        assert result["status"] == "insufficient_data"
        assert result["extracted"] == []

    def test_extracts_domain_rework(self, seeded_conn: sqlite3.Connection) -> None:
        result = learn_extract(seeded_conn, min_occurrences=3)
        assert result["status"] == "ok"
        # BACKEND has 3 reworks out of 5 = 60%
        backend_patterns = [
            p
            for p in result["extracted"]
            if "BACKEND" in p["pattern"] and "rework" in p["pattern"].lower()
        ]
        assert len(backend_patterns) >= 1
        assert backend_patterns[0]["confidence"] > 0

    def test_no_false_positive_frontend(self, seeded_conn: sqlite3.Connection) -> None:
        result = learn_extract(seeded_conn, min_occurrences=3)
        # FRONTEND only has 1 rework — shouldn't meet min_occurrences=3
        frontend_rework = [
            p
            for p in result["extracted"]
            if "FRONTEND" in p["pattern"] and "rework" in p["pattern"].lower()
        ]
        assert len(frontend_rework) == 0

    def test_idempotent(self, seeded_conn: sqlite3.Connection) -> None:
        learn_extract(seeded_conn, min_occurrences=3)
        result2 = learn_extract(seeded_conn, min_occurrences=3)
        # Second run should update, not create duplicates
        for p in result2["extracted"]:
            assert p["action"] == "updated"

    def test_min_occurrences_respected(self, seeded_conn: sqlite3.Connection) -> None:
        result = learn_extract(seeded_conn, min_occurrences=10)
        # With min_occurrences=10, no pattern should be extracted
        assert result["extracted"] == []

    def test_returns_analysis_stats(self, seeded_conn: sqlite3.Connection) -> None:
        result = learn_extract(seeded_conn, min_occurrences=3)
        assert "total_outcomes_analyzed" in result
        assert result["total_outcomes_analyzed"] == 8


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


class TestPatternIdentityDedup:
    """TASK-206: the running task count embedded in mined pattern text used
    to be part of the dedup identity, so every extraction run (count grew)
    inserted a NEW snapshot row — the Memory page filled with near-identical
    'INFRA succeeds … (32/32)' / '(40/40)' / '(83/83)' rows. Identity is now
    count-agnostic so a re-mined fact updates its single row."""

    def test_pattern_identity_strips_counts(self) -> None:
        from tools._learning_store import _pattern_identity

        a = _pattern_identity("INFRA domain succeeds at 100% (32/32 tasks) — reliable baseline")
        b = _pattern_identity("INFRA domain succeeds at 100% (83/83 tasks) — reliable baseline")
        assert a == b  # same fact, different snapshot count
        # distinct facts must NOT collide
        c = _pattern_identity("DOCS domain succeeds at 100% (6/6 tasks) — reliable baseline")
        assert a != c

    def test_growing_count_updates_not_duplicates(self, seeded_conn: sqlite3.Connection) -> None:
        from tools._learning_store import _upsert_pattern

        first = _upsert_pattern(
            seeded_conn,
            pattern="INFRA domain succeeds at 100% (40/40 tasks) — reliable baseline",
            memory_type="pattern",
            domain="INFRA",
            source="learn_extract",
            confidence=0.6,
            concepts="[]",
        )
        assert first["action"] == "created"
        second = _upsert_pattern(
            seeded_conn,
            pattern="INFRA domain succeeds at 100% (83/83 tasks) — reliable baseline",
            memory_type="pattern",
            domain="INFRA",
            source="learn_extract",
            confidence=0.7,
            concepts="[]",
        )
        assert second["action"] == "updated"
        assert second["id"] == first["id"]
        rows = seeded_conn.execute(
            "SELECT pattern, times_seen, times_validated FROM learned_patterns WHERE domain = 'INFRA'"
        ).fetchall()
        assert len(rows) == 1  # one row, not two snapshots
        assert "83/83" in rows[0]["pattern"]  # text refreshed to latest count
        assert rows[0]["times_seen"] == 1  # re-mine bumped the occurrence counter
        assert (rows[0]["times_validated"] or 0) == 0  # not a real validation

    def test_collapse_merges_legacy_snapshots(self, seeded_conn: sqlite3.Connection) -> None:
        from tools.learning import _collapse_duplicate_patterns

        for n in (22, 29, 31, 32, 40, 83):
            seeded_conn.execute(
                "INSERT INTO learned_patterns (pattern, domain, confidence, times_validated) "
                "VALUES (?, 'INFRA', 0.5, 0)",
                (f"INFRA domain succeeds at 100% ({n}/{n} tasks) — reliable baseline",),
            )
        seeded_conn.commit()
        removed = _collapse_duplicate_patterns(seeded_conn)
        assert removed == 5  # 6 snapshots → 1 survivor
        rows = seeded_conn.execute(
            "SELECT COUNT(*) FROM learned_patterns WHERE domain = 'INFRA'"
        ).fetchone()[0]
        assert rows == 1
        # second pass is idempotent — nothing left to collapse
        assert _collapse_duplicate_patterns(seeded_conn) == 0


# ---------------------------------------------------------------------------
# cos_learn_suggest
# ---------------------------------------------------------------------------


class TestLearnSuggest:
    def test_empty_db(self, conn: sqlite3.Connection) -> None:
        result = learn_suggest(conn)
        assert result["suggestions"] == []

    def test_returns_active_patterns(self, seeded_conn: sqlite3.Connection) -> None:
        # First extract to create patterns
        learn_extract(seeded_conn, min_occurrences=3)
        result = learn_suggest(seeded_conn, domain="BACKEND")
        assert result["count"] > 0
        for s in result["suggestions"]:
            assert s["reason"] in ("active", "fading")

    def test_domain_filter(self, seeded_conn: sqlite3.Connection) -> None:
        # Add patterns for different domains
        seeded_conn.execute(
            "INSERT INTO learned_patterns (pattern, domain, confidence) VALUES (?, ?, ?)",
            ("INFRA only pattern", "INFRA", 0.7),
        )
        seeded_conn.commit()
        result = learn_suggest(seeded_conn, domain="INFRA")
        patterns = [s["pattern"] for s in result["suggestions"]]
        assert "INFRA only pattern" in patterns

    def test_fading_patterns_surface(self, seeded_conn: sqlite3.Connection) -> None:
        # Create a fading pattern (0.2-0.4 confidence, established via times_seen)
        seeded_conn.execute(
            "INSERT INTO learned_patterns (pattern, domain, confidence, times_seen, "
            "last_validated) VALUES (?, ?, ?, ?, datetime('now', '-15 days'))",
            ("Fading BACKEND pattern", "BACKEND", 0.3, 2),
        )
        seeded_conn.commit()
        result = learn_suggest(seeded_conn, domain="BACKEND")
        fading = [s for s in result["suggestions"] if s["reason"] == "fading"]
        assert len(fading) >= 1

    def test_limit(self, seeded_conn: sqlite3.Connection) -> None:
        for i in range(10):
            seeded_conn.execute(
                "INSERT INTO learned_patterns (pattern, domain, confidence) VALUES (?, ?, ?)",
                (f"Pattern {i}", "BACKEND", 0.5 + i * 0.03),
            )
        seeded_conn.commit()
        result = learn_suggest(seeded_conn, domain="BACKEND", limit=3)
        assert result["count"] <= 3

    def test_excludes_stat_patterns(self, seeded_conn: sqlite3.Connection) -> None:
        seeded_conn.execute(
            "INSERT INTO learned_patterns (pattern, memory_type, domain, confidence) "
            "VALUES ('BACKEND domain succeeds at 100% — reliable baseline', 'stat', 'BACKEND', 0.85)"
        )
        seeded_conn.commit()
        result = learn_suggest(seeded_conn, domain="BACKEND")
        patterns = [s["pattern"] for s in result["suggestions"]]
        assert all("succeeds at 100%" not in p for p in patterns)


# ---------------------------------------------------------------------------
# cos_learn_validate
# ---------------------------------------------------------------------------


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
            "tools.learning._read_session_id_for_validate",
            lambda: next(sessions),
        )

        result1 = learn_validate(seeded_conn, pattern_id=pid, was_helpful=True)
        result2 = learn_validate(seeded_conn, pattern_id=pid, was_helpful=True)
        normal_boost = boost_success(result1["new_confidence"]) - result1["new_confidence"]
        actual_boost = result2["new_confidence"] - result1["new_confidence"]
        assert actual_boost >= normal_boost


# ---------------------------------------------------------------------------
# self-validation throttle
# ---------------------------------------------------------------------------


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
            "tools.learning._read_session_id_for_validate",
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
            "tools.learning._read_session_id_for_validate",
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
            "tools.learning._read_session_id_for_validate",
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
            "tools.learning._read_session_id_for_validate",
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


# ---------------------------------------------------------------------------
# evidence-based defaults (learn_narrative + _upsert_pattern)
# ---------------------------------------------------------------------------


class TestG6EvidenceBasedDefaults:
    def test_learn_narrative_creates_volatile_agent_self(
        self, seeded_conn: sqlite3.Connection
    ) -> None:
        """Previously learn_narrative inserted at confidence=0.7 impact=0.85.
        Audit A7 — self-fabricated breakthroughs with high trust. G.6 drops
        those defaults to 0.3 / 0.5 and stamps provenance=agent_self."""
        from tools._learning_narrative import learn_narrative

        res = learn_narrative(
            seeded_conn,
            task_id="TASK-100",
            what_failed="tried float rounding",
            what_worked="switched to Decimal.quantize",
            key_insight="Money must use Decimal",
        )
        assert "pattern_id" in res
        row = seeded_conn.execute(
            "SELECT confidence, impact_score, trust_tier, provenance "
            "FROM learned_patterns WHERE id = ?",
            (res["pattern_id"],),
        ).fetchone()
        assert row["confidence"] == 0.3
        assert row["impact_score"] == 0.5
        assert row["trust_tier"] == "volatile"
        assert row["provenance"] == "agent_self"

    def test_learn_extract_stamps_extracted_provenance(
        self, seeded_conn: sqlite3.Connection
    ) -> None:
        """Patterns mined from task_outcomes carry provenance=extracted_from_outcome."""
        result = learn_extract(seeded_conn, min_occurrences=3)
        assert result["status"] == "ok"
        # Fetch any extracted learned_patterns row with source=learn_extract
        rows = seeded_conn.execute(
            "SELECT provenance, trust_tier FROM learned_patterns WHERE source = 'learn_extract'"
        ).fetchall()
        assert len(rows) >= 1
        for r in rows:
            assert r["provenance"] == "extracted_from_outcome"
            # Still volatile — needs real validations before promotion
            assert r["trust_tier"] == "volatile"

    def test_upsert_pattern_explicit_provenance_override(
        self, seeded_conn: sqlite3.Connection
    ) -> None:
        from tools._learning_store import _upsert_pattern

        res = _upsert_pattern(
            seeded_conn,
            pattern="user told us this directly",
            memory_type="decision",
            domain="BACKEND",
            source="custom",
            confidence=0.5,
            concepts="[]",
            provenance="user_directive",
        )
        assert res["action"] == "created"
        row = seeded_conn.execute(
            "SELECT provenance FROM learned_patterns WHERE id = ?",
            (res["id"],),
        ).fetchone()
        assert row[0] == "user_directive"

    def test_upsert_pattern_unknown_source_falls_back_agent_self(
        self, seeded_conn: sqlite3.Connection
    ) -> None:
        from tools._learning_store import _upsert_pattern

        res = _upsert_pattern(
            seeded_conn,
            pattern="unknown source test",
            memory_type="pattern",
            domain=None,
            source="mystery",
            confidence=0.4,
            concepts="[]",
        )
        row = seeded_conn.execute(
            "SELECT provenance FROM learned_patterns WHERE id = ?",
            (res["id"],),
        ).fetchone()
        assert row[0] == "agent_self"


# ---------------------------------------------------------------------------
# inline embedding side effects
# ---------------------------------------------------------------------------

import embeddings
from tools._learning_narrative import learn_narrative
from tools._learning_store import _upsert_pattern

REQUIRES_RAG = pytest.mark.skipif(
    not embeddings.is_available(),
    reason="sentence-transformers + numpy not installed (uv sync --extra rag)",
)


class TestPatternEmbeddingIntegration:
    """Verify _upsert_pattern creates a corresponding embeddings row."""

    @REQUIRES_RAG
    def test_upsert_pattern_creates_embedding(self, conn: sqlite3.Connection) -> None:
        result = _upsert_pattern(
            conn,
            pattern="Always prefer service layer for DB writes",
            memory_type="pattern",
            domain="BACKEND",
            source="test",
            confidence=0.6,
            concepts="backend service layer",
        )
        assert result["action"] == "created"
        pattern_id = result["id"]

        row = conn.execute(
            "SELECT id, source_table, source_id FROM embeddings "
            "WHERE source_table = 'learned_patterns' AND source_id = ?",
            (pattern_id,),
        ).fetchone()
        assert row is not None, "expected embedding row for new pattern"

    @REQUIRES_RAG
    def test_upsert_pattern_updates_embedding_on_concept_change(
        self, conn: sqlite3.Connection
    ) -> None:
        first = _upsert_pattern(
            conn,
            pattern="Edge case test pattern",
            memory_type="pattern",
            domain="BACKEND",
            source="test",
            confidence=0.5,
            concepts="auth login",
        )
        # Second call: same pattern + domain → reuses row, may update concepts
        second = _upsert_pattern(
            conn,
            pattern="Edge case test pattern",
            memory_type="pattern",
            domain="BACKEND",
            source="test",
            confidence=0.7,
            concepts="auth login session",
        )
        assert first["id"] == second["id"]
        row = conn.execute(
            "SELECT id FROM embeddings WHERE source_table='learned_patterns' AND source_id=?",
            (first["id"],),
        ).fetchone()
        assert row is not None

    def test_upsert_pattern_succeeds_without_rag(
        self, conn: sqlite3.Connection, monkeypatch
    ) -> None:
        """Pattern upsert must succeed even when embeddings are unavailable."""
        monkeypatch.setattr(embeddings, "is_available", lambda: False)
        result = _upsert_pattern(
            conn,
            pattern="Pattern without embedding",
            memory_type="pattern",
            domain="BACKEND",
            source="test",
            confidence=0.5,
            concepts="ignored",
        )
        assert result["action"] == "created"


class TestSemanticConsolidation:
    """B5 — merge semantically near-duplicate lessons; keep distinct ones."""

    def test_no_op_without_rag(self, conn: sqlite3.Connection, monkeypatch) -> None:
        monkeypatch.setattr(embeddings, "is_available", lambda: False)
        from tools.learning import _consolidate_semantic_duplicates

        assert _consolidate_semantic_duplicates(conn) == 0

    @REQUIRES_RAG
    @pytest.mark.real_embeddings
    def test_merges_near_duplicates(self, conn: sqlite3.Connection) -> None:
        from tools.learning import _consolidate_semantic_duplicates

        _upsert_pattern(
            conn,
            pattern="Always parametrize SQL queries to prevent injection",
            memory_type="lesson",
            domain=None,
            source="friction",
            confidence=0.6,
            concepts="[]",
        )
        _upsert_pattern(
            conn,
            pattern="Always use parametrized SQL queries to avoid injection attacks",
            memory_type="lesson",
            domain="BACKEND",
            source="friction",
            confidence=0.5,
            concepts="[]",
        )
        before = conn.execute("SELECT COUNT(*) FROM learned_patterns").fetchone()[0]
        merged = _consolidate_semantic_duplicates(conn, threshold=0.75)
        after = conn.execute("SELECT COUNT(*) FROM learned_patterns").fetchone()[0]
        assert merged >= 1
        assert after == before - merged

    @REQUIRES_RAG
    def test_keeps_distinct_lessons(self, conn: sqlite3.Connection) -> None:
        from tools.learning import _consolidate_semantic_duplicates

        _upsert_pattern(
            conn,
            pattern="Load the graph-explorer skill before editing core Python",
            memory_type="lesson",
            domain=None,
            source="friction",
            confidence=0.6,
            concepts="[]",
        )
        _upsert_pattern(
            conn,
            pattern="Use Decimal not float for money calculations",
            memory_type="lesson",
            domain=None,
            source="friction",
            confidence=0.6,
            concepts="[]",
        )
        assert _consolidate_semantic_duplicates(conn, threshold=0.85) == 0


@pytest.fixture
def project_conn(tmp_path: Path) -> sqlite3.Connection:
    """DB in <tmp>/.coding-os/coding-os.db with a sibling docs/ dir."""
    state_dir = tmp_path / ".coding-os"
    state_dir.mkdir()
    (tmp_path / "docs").mkdir()
    c = init_db(state_dir / "coding-os.db")
    yield c
    c.close()


class TestGeneralizeLessons:
    """B3 — cluster related lessons into a human-review draft; never auto-write rules."""

    def test_no_op_without_rag(self, project_conn: sqlite3.Connection, monkeypatch) -> None:
        monkeypatch.setattr(embeddings, "is_available", lambda: False)
        from tools.learning import generalize_lessons

        assert generalize_lessons(project_conn)["drafts"] == []

    @REQUIRES_RAG
    def test_writes_draft_for_cluster(
        self, project_conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        from tools.learning import generalize_lessons

        for p in (
            "Parametrize SQL queries to prevent injection",
            "Use parametrized SQL to avoid injection attacks",
            "Bind SQL parameters instead of string building to stop injection",
        ):
            _upsert_pattern(
                project_conn,
                pattern=p,
                memory_type="lesson",
                domain=None,
                source="friction",
                confidence=0.6,
                concepts="[]",
            )
        res = generalize_lessons(project_conn, min_cluster=3, sim_threshold=0.4)
        assert len(res["drafts"]) >= 1
        draft = tmp_path / ".coding-os" / "memory" / "drafts" / res["drafts"][0]
        assert draft.exists()
        assert "Generalize" in draft.read_text(encoding="utf-8")

    @REQUIRES_RAG
    def test_below_min_cluster_no_draft(self, project_conn: sqlite3.Connection) -> None:
        from tools.learning import generalize_lessons

        _upsert_pattern(
            project_conn,
            pattern="Use Decimal for money calculations",
            memory_type="lesson",
            domain=None,
            source="friction",
            confidence=0.6,
            concepts="[]",
        )
        assert generalize_lessons(project_conn, min_cluster=3)["drafts"] == []


class TestLearnNarrativeEmbedding:
    @REQUIRES_RAG
    def test_narrative_embeds_outcome_history_and_pattern(self, conn: sqlite3.Connection) -> None:
        # Seed task_outcomes so the narrative path can find a domain
        conn.execute(
            "INSERT INTO task_outcomes (task_id, type, domain, complexity, outcome) "
            "VALUES (?, ?, ?, ?, ?)",
            ("TASK-501", "fix", "BACKEND", "COMPLICATED", "success"),
        )
        conn.commit()

        result = learn_narrative(
            conn,
            task_id="TASK-501",
            what_failed="Tried mocking the JWT library",
            what_worked="Used real token generation in test fixtures",
            key_insight="Mock at the boundary, not at the leaf",
        )
        assert "history_id" in result
        assert "pattern_id" in result

        history_row = conn.execute(
            "SELECT id FROM embeddings WHERE source_table='outcome_history' AND source_id=?",
            (result["history_id"],),
        ).fetchone()
        pattern_row = conn.execute(
            "SELECT id FROM embeddings WHERE source_table='learned_patterns' AND source_id=?",
            (result["pattern_id"],),
        ).fetchone()
        assert history_row is not None
        assert pattern_row is not None

    def test_narrative_succeeds_without_rag(self, conn: sqlite3.Connection, monkeypatch) -> None:
        monkeypatch.setattr(embeddings, "is_available", lambda: False)
        result = learn_narrative(
            conn,
            task_id="TASK-502",
            key_insight="Some lesson",
        )
        assert "history_id" in result
        assert "pattern_id" in result


# ---------------------------------------------------------------------------
class TestTimesSeenSplit:
    def test_remine_bumps_times_seen_not_times_validated(self, conn: sqlite3.Connection) -> None:
        conn.row_factory = sqlite3.Row
        from tools._learning_store import _upsert_pattern

        kw = {
            "memory_type": "pattern",
            "domain": "BACKEND",
            "source": "mined",
            "confidence": 0.6,
            "concepts": "[]",
        }
        first = _upsert_pattern(conn, pattern="Always use the services layer for DB writes", **kw)
        pid = first["id"]
        assert first["action"] == "created"
        for _ in range(2):
            _upsert_pattern(conn, pattern="Always use the services layer for DB writes", **kw)
        row = conn.execute(
            "SELECT times_seen, times_validated FROM learned_patterns WHERE id = ?", (pid,)
        ).fetchone()
        assert row["times_seen"] == 2  # two re-mines are occurrences, not validations
        assert (row["times_validated"] or 0) == 0  # never really validated

    def test_remine_does_not_raise_penalized_confidence(self, conn: sqlite3.Connection) -> None:
        conn.row_factory = sqlite3.Row
        from tools._learning_store import _upsert_pattern

        kw = {"memory_type": "pattern", "domain": "BACKEND", "source": "mined", "concepts": "[]"}
        pid = _upsert_pattern(conn, pattern="Guard None before deref", confidence=0.4, **kw)["id"]
        # A validation (LTD) penalized the belief down to 0.2.
        conn.execute("UPDATE learned_patterns SET confidence = 0.2 WHERE id = ?", (pid,))
        conn.commit()
        # A re-mine arriving with HIGHER extract confidence must not resurrect it:
        # confidence is validation-owned; re-extraction only bumps times_seen.
        _upsert_pattern(conn, pattern="Guard None before deref", confidence=0.9, **kw)
        row = conn.execute(
            "SELECT confidence, times_seen FROM learned_patterns WHERE id = ?", (pid,)
        ).fetchone()
        assert row["confidence"] == pytest.approx(0.2)  # LTD survives re-extraction
        assert row["times_seen"] == 1

    def test_collapse_folds_times_seen_into_survivor(self, conn: sqlite3.Connection) -> None:
        conn.row_factory = sqlite3.Row
        from tools.learning import _collapse_duplicate_patterns

        for seen in (2, 5):
            conn.execute(
                "INSERT INTO learned_patterns (pattern, memory_type, domain, source, confidence, "
                "concepts, times_seen, times_validated) "
                "VALUES (?, 'pattern', 'BACKEND', 'mined', 0.6, '[]', ?, 0)",
                ("Prefer composition over inheritance", seen),
            )
        conn.commit()
        removed = _collapse_duplicate_patterns(conn)
        assert removed == 1
        rows = conn.execute(
            "SELECT times_seen FROM learned_patterns WHERE pattern = 'Prefer composition over inheritance'"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["times_seen"] == 2 + 5 + 1  # summed occurrences + 1 collapsed loser
