"""
Tests for MCP memory tools (TASK-142).

Covers 5-signal ranking, FTS5/LIKE fallback, access_count boost,
timeline, details, promote, and empty DB handling.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import init_db
from tools.memory import (
    _access_score,
    _compute_score,
    _recency_score,
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
    """DB with sample observations and learned patterns."""
    observations = [
        (
            "sess-1",
            "Read",
            "Django migration fix",
            "Fixed missing migration for User model",
            '["django","migration","backend"]',
            "discovery",
            0.7,
        ),
        (
            "sess-1",
            "Edit",
            "PostgreSQL index optimization",
            "Added covering index to products table",
            '["postgres","index","performance"]',
            "decision",
            0.8,
        ),
        (
            "sess-2",
            "Bash",
            "Frontend build error",
            "Webpack config had wrong entry point",
            '["frontend","webpack","build"]',
            "error",
            0.6,
        ),
        (
            "sess-2",
            "Read",
            "API rate limiting setup",
            "Configured Django throttling classes",
            '["api","django","throttling"]',
            "config",
            0.5,
        ),
        (
            "sess-3",
            "Edit",
            "Celery task retry fix",
            "Added exponential backoff to payment tasks",
            '["celery","retry","backend"]',
            "pattern",
            0.9,
        ),
    ]
    for sess, tool, title, narrative, concepts, mtype, impact in observations:
        conn.execute(
            "INSERT INTO observations (session_id, tool_name, title, narrative, concepts, "
            "memory_type, impact_score) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (sess, tool, title, narrative, concepts, mtype, impact),
        )

    patterns = [
        (
            "Always use services layer for DB writes",
            "pattern",
            "BACKEND",
            "task-done",
            0.7,
            0.1,
            0.6,
            '["django","services","orm"]',
            5,
            1,
            3,
        ),
        (
            "Run lint before commit",
            "workflow",
            "INFRA",
            "observation",
            0.5,
            0.1,
            0.4,
            '["lint","commit","workflow"]',
            2,
            0,
            1,
        ),
        (
            "Use factory_boy for test fixtures",
            "pattern",
            "BACKEND",
            "observation",
            0.8,
            0.05,
            0.7,
            '["testing","factory","django"]',
            8,
            0,
            7,
        ),
        (
            "Check FTS5 availability before search",
            "decision",
            "INFRA",
            "task-done",
            0.3,
            0.1,
            0.3,
            '["fts5","sqlite","search"]',
            1,
            0,
            0,
        ),
    ]
    for (
        pattern,
        mtype,
        domain,
        source,
        conf,
        decay,
        impact,
        concepts,
        tv,
        tviol,
        access,
    ) in patterns:
        conn.execute(
            "INSERT INTO learned_patterns (pattern, memory_type, domain, source, confidence, "
            "decay_rate, impact_score, concepts, times_validated, times_violated, access_count) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (pattern, mtype, domain, source, conf, decay, impact, concepts, tv, tviol, access),
        )

    # Add task outcomes for timeline
    conn.execute(
        "INSERT INTO task_outcomes (task_id, type, domain, complexity, outcome) "
        "VALUES (?, ?, ?, ?, ?)",
        ("TASK-100", "feat", "BACKEND", "COMPLICATED", "success"),
    )
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# 5-signal ranking formula
# ---------------------------------------------------------------------------


import embeddings
from tools.memory import _jaccard, _mmr_select, _rrf_fuse, _tokenize

REQUIRES_RAG = pytest.mark.skipif(
    not embeddings.is_available(),
    reason="sentence-transformers + numpy not installed (uv sync --extra rag)",
)


class TestRankingFormula:
    def test_recency_score_zero_days(self) -> None:
        assert _recency_score(0) == 1.0

    def test_recency_score_30_days(self) -> None:
        assert _recency_score(30) == pytest.approx(0.5)

    def test_recency_score_large(self) -> None:
        assert _recency_score(999) < 0.05

    def test_access_score_zero(self) -> None:
        assert _access_score(0) == 0.0

    def test_access_score_ten(self) -> None:
        assert _access_score(10) == 1.0

    def test_access_score_capped(self) -> None:
        assert _access_score(100) == 1.0

    def test_compute_score_ranges(self) -> None:
        score = _compute_score(
            relevance=1.0,
            confidence=1.0,
            recency_days=0,
            impact=1.0,
            access_count=10,
        )
        assert 0.0 < score <= 1.0

    def test_compute_score_minimum(self) -> None:
        score = _compute_score(
            relevance=0.0,
            confidence=0.0,
            recency_days=999,
            impact=0.0,
            access_count=0,
        )
        assert score >= 0.0

    def test_higher_confidence_ranks_higher(self) -> None:
        low = _compute_score(0.5, 0.2, 10, 0.5, 0)
        high = _compute_score(0.5, 0.9, 10, 0.5, 0)
        assert high > low

    def test_higher_impact_ranks_higher(self) -> None:
        low = _compute_score(0.5, 0.5, 10, 0.1, 0)
        high = _compute_score(0.5, 0.5, 10, 0.9, 0)
        assert high > low


class TestRankFusionDiversity:
    def test_tokenize_and_jaccard(self) -> None:
        assert _tokenize("Cookie SameSite-flag") == {"cookie", "samesite", "flag"}
        assert _jaccard({"a", "b"}, {"a", "b"}) == pytest.approx(1.0)
        assert _jaccard({"a", "b", "c"}, {"a"}) == pytest.approx(1 / 3)
        assert _jaccard(set(), {"a"}) == 0.0

    def test_rrf_rewards_presence_in_both_lists(self) -> None:
        both = {"source_table": "observations", "id": 1, "score": 1.0, "semantic_score": 0.9}
        lex_only = {"source_table": "observations", "id": 2, "score": 0.9, "semantic_score": 0.0}
        sem_only = {"source_table": "observations", "id": 3, "score": 0.1, "semantic_score": 0.95}
        _rrf_fuse([both, lex_only, sem_only])
        # a row ranked in BOTH lexical and semantic lists fuses above one in only one
        assert both["score"] > lex_only["score"]
        assert both["score"] > sem_only["score"]

    def test_mmr_drops_near_duplicate_from_slice(self) -> None:
        top = {
            "source_table": "observations",
            "id": 1,
            "title": "cookie samesite flag",
            "concepts": "auth session",
            "score": 1.0,
        }
        near = {
            "source_table": "observations",
            "id": 2,
            "title": "samesite cookie attribute",
            "concepts": "auth session",
            "score": 0.6,
        }
        diverse = {
            "source_table": "observations",
            "id": 3,
            "title": "rate limit window",
            "concepts": "perf throughput",
            "score": 0.55,
        }
        picked = _mmr_select([top, near, diverse], limit=2)
        ids = [c["id"] for c in picked]
        assert ids[0] == 1  # highest relevance first
        assert ids[1] == 3  # diverse beats the near-duplicate for the 2nd slot

    def test_mmr_keeps_relevant_near_dup_over_irrelevant_distinct(self) -> None:
        # Realistic RRF magnitudes (~0.015-0.033): a clearly-more-relevant near-
        # duplicate must NOT be demoted below a far-less-relevant distinct row
        # (regression guard for the un-normalized-relevance MMR bug).
        top = {
            "source_table": "observations",
            "id": 1,
            "title": "cookie samesite flag",
            "concepts": "auth session",
            "score": 0.0328,
        }
        near = {
            "source_table": "observations",
            "id": 2,
            "title": "samesite cookie attribute",
            "concepts": "auth session",
            "score": 0.0320,
        }
        distinct = {
            "source_table": "observations",
            "id": 3,
            "title": "rate limit window",
            "concepts": "perf throughput",
            "score": 0.0150,
        }
        picked = _mmr_select([top, near, distinct], limit=2)
        ids = [c["id"] for c in picked]
        assert ids[0] == 1
        assert ids[1] == 2  # the relevant near-dup beats the irrelevant distinct row


# ---------------------------------------------------------------------------
# Retrieval must not move confidence (memory.md § Memory hygiene rules)
# ---------------------------------------------------------------------------


class TestReadingIsNotEvidence:
    """cos_details records that a pattern was read, never that it is truer.

    _boost_access used to also run `confidence = MIN(0.95, confidence + 0.02)`,
    so ~23 detail views drove any belief to the ceiling without one confirming
    observation — while memory.md promised confidence moves only via
    cos_learn_validate. The two contracts disagreed and the code won.
    """

    def _confidence(self, conn: sqlite3.Connection, pattern_id: int) -> float:
        row = conn.execute(
            "SELECT confidence FROM learned_patterns WHERE id = ?", (pattern_id,)
        ).fetchone()
        return float(row[0])

    def test_repeated_details_leaves_confidence_untouched(
        self, seeded_conn: sqlite3.Connection
    ) -> None:
        from tools._memory_ranking import _boost_access

        before = self._confidence(seeded_conn, 1)
        for _ in range(40):
            _boost_access(seeded_conn, "learned_patterns", 1)
        seeded_conn.commit()

        assert self._confidence(seeded_conn, 1) == pytest.approx(before)

    def test_details_still_records_access(self, seeded_conn: sqlite3.Connection) -> None:
        from tools._memory_ranking import _boost_access

        row = seeded_conn.execute(
            "SELECT access_count FROM learned_patterns WHERE id = 1"
        ).fetchone()
        before = int(row[0] or 0)

        _boost_access(seeded_conn, "learned_patterns", 1)
        seeded_conn.commit()

        row = seeded_conn.execute(
            "SELECT access_count, last_accessed_at FROM learned_patterns WHERE id = 1"
        ).fetchone()
        assert int(row[0]) == before + 1
        assert row[1] is not None

    def test_access_still_reaches_ranking(self) -> None:
        # Frequency keeps its influence — through the access signal, not through
        # the confidence term it used to inflate.
        read_often = _compute_score(
            relevance=0.5, confidence=0.5, recency_days=1.0, impact=0.5, access_count=10
        )
        read_once = _compute_score(
            relevance=0.5, confidence=0.5, recency_days=1.0, impact=0.5, access_count=0
        )
        assert read_often > read_once
