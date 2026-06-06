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
    generate_feedback_drafts,
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
        result1 = learn_extract(seeded_conn, min_occurrences=3)
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


class TestPatternIdentityDedup:
    """TASK-206: the running task count embedded in mined pattern text used
    to be part of the dedup identity, so every extraction run (count grew)
    inserted a NEW snapshot row — the Memory page filled with near-identical
    'INFRA succeeds … (32/32)' / '(40/40)' / '(83/83)' rows. Identity is now
    count-agnostic so a re-mined fact updates its single row."""

    def test_pattern_identity_strips_counts(self) -> None:
        from tools.learning import _pattern_identity

        a = _pattern_identity("INFRA domain succeeds at 100% (32/32 tasks) — reliable baseline")
        b = _pattern_identity("INFRA domain succeeds at 100% (83/83 tasks) — reliable baseline")
        assert a == b  # same fact, different snapshot count
        # distinct facts must NOT collide
        c = _pattern_identity("DOCS domain succeeds at 100% (6/6 tasks) — reliable baseline")
        assert a != c

    def test_growing_count_updates_not_duplicates(self, seeded_conn: sqlite3.Connection) -> None:
        from tools.learning import _upsert_pattern

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
            "SELECT pattern, times_validated FROM learned_patterns WHERE domain = 'INFRA'"
        ).fetchall()
        assert len(rows) == 1  # one row, not two snapshots
        assert "83/83" in rows[0]["pattern"]  # text refreshed to latest count
        assert rows[0]["times_validated"] == 1  # re-confirmation bumped

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
        # Create a fading pattern (0.2-0.4 confidence, validated)
        seeded_conn.execute(
            "INSERT INTO learned_patterns (pattern, domain, confidence, times_validated, "
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
        from tools.learning import learn_narrative

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
        from tools.learning import _upsert_pattern

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
        from tools.learning import _upsert_pattern

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
# Auto-feedback generation (TASK-147)
# ---------------------------------------------------------------------------


class TestFeedbackDrafts:
    def test_empty_db(self, conn: sqlite3.Connection) -> None:
        result = generate_feedback_drafts(conn)
        assert result["count"] == 0
        assert result["drafts"] == []

    def test_below_threshold(self, conn: sqlite3.Connection) -> None:
        # Only 2 reworks — below threshold of 3
        for i in range(2):
            conn.execute(
                "INSERT INTO task_outcomes (task_id, type, domain, complexity, outcome, skills_used) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (f"TASK-{i}", "feat", "BACKEND", "CLEAR", "rework", "python-django"),
            )
        conn.commit()
        result = generate_feedback_drafts(conn)
        assert result["count"] == 0

    def test_generates_draft(self, seeded_conn: sqlite3.Connection) -> None:
        result = generate_feedback_drafts(seeded_conn, min_rework=3)
        # seeded_conn has 3 BACKEND reworks with python-django
        backend_drafts = [d for d in result["drafts"] if d["domain"] == "BACKEND"]
        assert len(backend_drafts) >= 1

    def test_draft_has_required_fields(self, seeded_conn: sqlite3.Connection) -> None:
        result = generate_feedback_drafts(seeded_conn, min_rework=3)
        if result["count"] > 0:
            draft = result["drafts"][0]
            assert "filename" in draft
            assert "content" in draft
            assert "domain" in draft
            assert "skill" in draft
            assert "evidence_tasks" in draft
            assert "status: draft" in draft["content"]

    def test_draft_content_format(self, seeded_conn: sqlite3.Connection) -> None:
        result = generate_feedback_drafts(seeded_conn, min_rework=3)
        if result["count"] > 0:
            content = result["drafts"][0]["content"]
            assert "---" in content  # frontmatter
            assert "**Evidence:**" in content
            assert "**Suggested rule:**" in content
            assert "**Why:**" in content

    def test_no_duplicate_for_same_cluster(self, seeded_conn: sqlite3.Connection) -> None:
        r1 = generate_feedback_drafts(seeded_conn, min_rework=3)
        r2 = generate_feedback_drafts(seeded_conn, min_rework=3)
        # Same data should produce same drafts
        assert r1["count"] == r2["count"]


# ---------------------------------------------------------------------------
# inline embedding side effects
# ---------------------------------------------------------------------------

import embeddings  # noqa: E402
from tools.learning import _upsert_pattern, learn_narrative  # noqa: E402

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
# Filing-back: markdown artifact in docs/insights/
# ---------------------------------------------------------------------------

from tools.learning import (  # noqa: E402
    _derive_project_root,
    _file_back_narrative_safe,
    _format_narrative_markdown,
    _slugify,
)


@pytest.fixture
def project_conn(tmp_path: Path) -> sqlite3.Connection:
    """DB in <tmp>/.coding-os/coding-os.db with a sibling docs/ dir."""
    state_dir = tmp_path / ".coding-os"
    state_dir.mkdir()
    (tmp_path / "docs").mkdir()
    c = init_db(state_dir / "coding-os.db")
    yield c
    c.close()


class TestSlugify:
    def test_lowercases_and_dashes(self) -> None:
        assert _slugify("Mock AT THE Boundary") == "mock-at-the-boundary"

    def test_collapses_non_alnum_runs(self) -> None:
        assert _slugify("hello!!  world??") == "hello-world"

    def test_empty_input_returns_untitled(self) -> None:
        assert _slugify("   ") == "untitled"

    def test_truncates_to_max_len(self) -> None:
        result = _slugify("a" * 80, max_len=20)
        assert len(result) == 20


class TestDeriveProjectRoot:
    def test_project_root_from_coding_os_layout(
        self, project_conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        root = _derive_project_root(project_conn)
        assert root is not None
        assert root.resolve() == tmp_path.resolve()

    def test_returns_none_for_non_coding_os_layout(self, conn: sqlite3.Connection) -> None:
        # Default fixture DB sits at tmp_path/test.db (no .coding-os/)
        assert _derive_project_root(conn) is None


class TestFormatNarrativeMarkdown:
    def test_includes_task_id_and_insight_in_heading(self) -> None:
        md = _format_narrative_markdown(
            task_id="TASK-900",
            domain="BACKEND",
            key_insight="Mock at the boundary, not at the leaf",
            what_failed="Mocked the whole JWT lib",
            what_worked="Real tokens in test fixtures",
            history_id=42,
            pattern_id=99,
        )
        assert "# TASK-900: Mock at the boundary, not at the leaf" in md
        assert "**Domain:** BACKEND" in md
        assert "outcome_history#42" in md
        assert "learned_patterns#99" in md
        assert "Real tokens in test fixtures" in md

    def test_missing_failed_or_worked_renders_placeholder(self) -> None:
        md = _format_narrative_markdown(
            task_id="TASK-901",
            domain=None,
            key_insight="x",
            what_failed="",
            what_worked="",
            history_id=1,
            pattern_id=1,
        )
        assert "_(not recorded)_" in md
        assert "**Domain:** n/a" in md


class TestFileBackNarrative:
    def test_writes_markdown_under_docs_insights(
        self, project_conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        result = _file_back_narrative_safe(
            conn=project_conn,
            task_id="TASK-700",
            domain="BACKEND",
            key_insight="Mock at the boundary",
            what_failed="Mocked internals",
            what_worked="Mocked at the HTTP edge",
            history_id=7,
            pattern_id=11,
        )
        assert result is not None
        assert result.exists()
        target_dir = tmp_path / "docs" / "insights"
        assert result.parent.resolve() == target_dir.resolve()
        content = result.read_text(encoding="utf-8")
        assert "TASK-700" in content
        assert "Mock at the boundary" in content

    def test_skips_when_no_docs_dir(self, tmp_path: Path) -> None:
        state_dir = tmp_path / ".coding-os"
        state_dir.mkdir()
        # Deliberately NOT creating tmp_path/docs/
        c = init_db(state_dir / "coding-os.db")
        try:
            result = _file_back_narrative_safe(
                conn=c,
                task_id="TASK-701",
                domain=None,
                key_insight="x",
                what_failed="",
                what_worked="",
                history_id=1,
                pattern_id=1,
            )
            assert result is None
        finally:
            c.close()

    def test_skips_for_non_coding_os_layout(self, conn: sqlite3.Connection) -> None:
        result = _file_back_narrative_safe(
            conn=conn,
            task_id="TASK-702",
            domain=None,
            key_insight="x",
            what_failed="",
            what_worked="",
            history_id=1,
            pattern_id=1,
        )
        assert result is None

    def test_learn_narrative_reports_filed_path(
        self, project_conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        project_conn.execute(
            "INSERT INTO task_outcomes (task_id, type, domain, complexity, outcome) "
            "VALUES (?, ?, ?, ?, ?)",
            ("TASK-703", "fix", "BACKEND", "COMPLICATED", "success"),
        )
        project_conn.commit()

        result = learn_narrative(
            project_conn,
            task_id="TASK-703",
            what_failed="A",
            what_worked="B",
            key_insight="Lesson learned about retries",
        )
        assert result.get("filed_path")
        filed = Path(result["filed_path"])
        assert filed.exists()
        assert filed.parent.resolve() == (tmp_path / "docs" / "insights").resolve()

    def test_learn_narrative_no_filed_path_without_project_layout(
        self, conn: sqlite3.Connection
    ) -> None:
        result = learn_narrative(
            conn,
            task_id="TASK-704",
            key_insight="Some insight",
        )
        assert result.get("filed_path") is None

    def test_narrative_overwrites_same_slug(self, project_conn: sqlite3.Connection) -> None:
        first = _file_back_narrative_safe(
            conn=project_conn,
            task_id="TASK-705",
            domain="BACKEND",
            key_insight="Same insight",
            what_failed="v1",
            what_worked="v1",
            history_id=1,
            pattern_id=1,
        )
        second = _file_back_narrative_safe(
            conn=project_conn,
            task_id="TASK-705",
            domain="BACKEND",
            key_insight="Same insight",
            what_failed="v2-updated",
            what_worked="v2-updated",
            history_id=1,
            pattern_id=1,
        )
        assert first == second
        assert "v2-updated" in second.read_text(encoding="utf-8")
