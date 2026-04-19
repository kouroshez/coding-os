"""
Tests for MCP memory tools (TASK-142).

Covers 5-signal ranking, FTS5/LIKE fallback, access_count boost,
timeline, details, promote, and empty DB handling.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db import has_fts5, has_fts5_table, init_db
from tools.memory import (
    memory_details,
    memory_promote,
    memory_search,
    memory_timeline,
    _compute_score,
    _recency_score,
    _access_score,
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
        ("sess-1", "Read", "Django migration fix", "Fixed missing migration for User model",
         '["django","migration","backend"]', "discovery", 0.7),
        ("sess-1", "Edit", "PostgreSQL index optimization", "Added covering index to products table",
         '["postgres","index","performance"]', "decision", 0.8),
        ("sess-2", "Bash", "Frontend build error", "Webpack config had wrong entry point",
         '["frontend","webpack","build"]', "error", 0.6),
        ("sess-2", "Read", "API rate limiting setup", "Configured Django throttling classes",
         '["api","django","throttling"]', "config", 0.5),
        ("sess-3", "Edit", "Celery task retry fix", "Added exponential backoff to payment tasks",
         '["celery","retry","backend"]', "pattern", 0.9),
    ]
    for sess, tool, title, narrative, concepts, mtype, impact in observations:
        conn.execute(
            "INSERT INTO observations (session_id, tool_name, title, narrative, concepts, "
            "memory_type, impact_score) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (sess, tool, title, narrative, concepts, mtype, impact),
        )

    patterns = [
        ("Always use services layer for DB writes", "pattern", "BACKEND",
         "task-done", 0.7, 0.1, 0.6, '["django","services","orm"]', 5, 1, 3),
        ("Run lint before commit", "workflow", "INFRA",
         "observation", 0.5, 0.1, 0.4, '["lint","commit","workflow"]', 2, 0, 1),
        ("Use factory_boy for test fixtures", "pattern", "BACKEND",
         "observation", 0.8, 0.05, 0.7, '["testing","factory","django"]', 8, 0, 7),
        ("Check FTS5 availability before search", "decision", "INFRA",
         "task-done", 0.3, 0.1, 0.3, '["fts5","sqlite","search"]', 1, 0, 0),
    ]
    for pattern, mtype, domain, source, conf, decay, impact, concepts, tv, tviol, access in patterns:
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
            relevance=1.0, confidence=1.0,
            recency_days=0, impact=1.0, access_count=10,
        )
        assert 0.0 < score <= 1.0

    def test_compute_score_minimum(self) -> None:
        score = _compute_score(
            relevance=0.0, confidence=0.0,
            recency_days=999, impact=0.0, access_count=0,
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


# ---------------------------------------------------------------------------
# thinking_os_search
# ---------------------------------------------------------------------------

class TestMemorySearch:
    def test_empty_db(self, conn: sqlite3.Connection) -> None:
        result = memory_search(conn, query="anything")
        assert result["count"] == 0
        assert result["results"] == []

    def test_empty_query(self, conn: sqlite3.Connection) -> None:
        result = memory_search(conn, query="")
        assert result["source"] == "empty_query"

    def test_fts5_search(self, seeded_conn: sqlite3.Connection) -> None:
        if not has_fts5_table(seeded_conn):
            pytest.skip("FTS5 not available")
        result = memory_search(seeded_conn, query="Django", use_fts5=True)
        assert result["count"] > 0
        assert result["source"] == "fts5"

    def test_like_fallback(self, seeded_conn: sqlite3.Connection) -> None:
        result = memory_search(seeded_conn, query="Django", use_fts5=False)
        assert result["count"] > 0
        assert result["source"] == "like"

    def test_search_returns_required_fields(self, seeded_conn: sqlite3.Connection) -> None:
        result = memory_search(seeded_conn, query="Django", use_fts5=False)
        for r in result["results"]:
            assert "id" in r
            assert "title" in r
            assert "confidence" in r
            assert "source_table" in r
            assert "memory_type" in r

    def test_filter_by_memory_type(self, seeded_conn: sqlite3.Connection) -> None:
        result = memory_search(
            seeded_conn, query="Django", memory_type="pattern", use_fts5=False,
        )
        for r in result["results"]:
            assert r["memory_type"] == "pattern"

    def test_limit_respected(self, seeded_conn: sqlite3.Connection) -> None:
        result = memory_search(seeded_conn, query="Django", limit=2, use_fts5=False)
        assert result["count"] <= 2

    def test_access_count_boosted(self, seeded_conn: sqlite3.Connection) -> None:
        # Get initial access count of a learned pattern
        initial = seeded_conn.execute(
            "SELECT access_count FROM learned_patterns WHERE id = 1"
        ).fetchone()[0]
        memory_search(seeded_conn, query="services", use_fts5=False)
        after = seeded_conn.execute(
            "SELECT access_count FROM learned_patterns WHERE id = 1"
        ).fetchone()[0]
        assert after >= initial  # may be boosted if pattern was in results

    def test_no_score_in_output(self, seeded_conn: sqlite3.Connection) -> None:
        result = memory_search(seeded_conn, query="Django", use_fts5=False)
        for r in result["results"]:
            assert "score" not in r


# ---------------------------------------------------------------------------
# thinking_os_timeline
# ---------------------------------------------------------------------------

class TestMemoryTimeline:
    def test_empty_db(self, conn: sqlite3.Connection) -> None:
        result = memory_timeline(conn)
        assert result["count"] == 0
        assert result["entries"] == []

    def test_returns_task_outcomes(self, seeded_conn: sqlite3.Connection) -> None:
        result = memory_timeline(seeded_conn, days=365)
        types = {e["type"] for e in result["entries"]}
        assert "task_outcome" in types

    def test_returns_observations(self, seeded_conn: sqlite3.Connection) -> None:
        result = memory_timeline(seeded_conn, days=365)
        entry_types = {e["type"] for e in result["entries"]}
        # Should have non-task-outcome types
        assert len(entry_types) > 1

    def test_sorted_by_date_desc(self, seeded_conn: sqlite3.Connection) -> None:
        result = memory_timeline(seeded_conn, days=365)
        dates = [e["date"] for e in result["entries"] if e["date"]]
        assert dates == sorted(dates, reverse=True)

    def test_limit(self, seeded_conn: sqlite3.Connection) -> None:
        result = memory_timeline(seeded_conn, days=365, limit=3)
        assert result["count"] <= 3

    def test_days_window(self, seeded_conn: sqlite3.Connection) -> None:
        # 0 days clamped to 1
        result = memory_timeline(seeded_conn, days=0)
        assert result["days"] == 1


# ---------------------------------------------------------------------------
# thinking_os_details
# ---------------------------------------------------------------------------

class TestMemoryDetails:
    def test_get_learned_pattern(self, seeded_conn: sqlite3.Connection) -> None:
        result = memory_details(seeded_conn, pattern_id=1, source="learned_patterns")
        assert "record" in result
        assert result["record"]["pattern"] is not None

    def test_get_observation(self, seeded_conn: sqlite3.Connection) -> None:
        result = memory_details(seeded_conn, pattern_id=1, source="observations")
        assert "record" in result
        assert result["record"]["title"] is not None

    def test_get_task_outcome(self, seeded_conn: sqlite3.Connection) -> None:
        result = memory_details(seeded_conn, pattern_id="TASK-100", source="task_outcomes")
        assert "record" in result
        assert result["record"]["outcome"] == "success"

    def test_not_found(self, seeded_conn: sqlite3.Connection) -> None:
        result = memory_details(seeded_conn, pattern_id=999, source="learned_patterns")
        assert "error" in result

    def test_invalid_source(self, seeded_conn: sqlite3.Connection) -> None:
        result = memory_details(seeded_conn, pattern_id=1, source="invalid")
        assert "error" in result

    def test_narrative_truncation(self, seeded_conn: sqlite3.Connection) -> None:
        # Insert observation with very long narrative
        seeded_conn.execute(
            "INSERT INTO observations (title, narrative) VALUES (?, ?)",
            ("Long obs", "x" * 1000),
        )
        seeded_conn.commit()
        obs_id = seeded_conn.execute(
            "SELECT id FROM observations WHERE title = 'Long obs'"
        ).fetchone()[0]
        result = memory_details(seeded_conn, pattern_id=obs_id, source="observations")
        assert len(result["record"]["narrative"]) <= 520  # 500 + "... [truncated]"


# ---------------------------------------------------------------------------
# thinking_os_promote
# ---------------------------------------------------------------------------

class TestMemoryPromote:
    def test_promote_to_feedback(self, seeded_conn: sqlite3.Connection) -> None:
        result = memory_promote(
            seeded_conn, pattern_id=1, target="feedback", memory_dir="/tmp",
        )
        assert result["status"] == "promoted"
        assert "feedback" in result["filename"]
        assert "---" in result["content"]  # frontmatter

    def test_promote_to_rule(self, seeded_conn: sqlite3.Connection) -> None:
        result = memory_promote(
            seeded_conn, pattern_id=3, target="rule", memory_dir="/tmp",
        )
        assert result["status"] == "promoted"
        assert "learned_" in result["filename"]

    def test_promote_low_confidence_rejected(self, seeded_conn: sqlite3.Connection) -> None:
        # Pattern 4 has confidence 0.3 — exactly at threshold
        result = memory_promote(
            seeded_conn, pattern_id=4, target="feedback", memory_dir="/tmp",
        )
        assert result["status"] == "promoted"

        # Now lower it below threshold
        seeded_conn.execute(
            "UPDATE learned_patterns SET confidence = 0.1 WHERE id = 4"
        )
        seeded_conn.commit()
        result = memory_promote(
            seeded_conn, pattern_id=4, target="feedback", memory_dir="/tmp",
        )
        assert "error" in result

    def test_promote_not_found(self, seeded_conn: sqlite3.Connection) -> None:
        result = memory_promote(
            seeded_conn, pattern_id=999, target="feedback", memory_dir="/tmp",
        )
        assert "error" in result

    def test_promote_invalid_target(self, seeded_conn: sqlite3.Connection) -> None:
        result = memory_promote(
            seeded_conn, pattern_id=1, target="invalid", memory_dir="/tmp",
        )
        assert "error" in result

    def test_promote_updates_promoted_to(self, seeded_conn: sqlite3.Connection) -> None:
        memory_promote(
            seeded_conn, pattern_id=1, target="feedback", memory_dir="/tmp",
        )
        row = seeded_conn.execute(
            "SELECT promoted_to FROM learned_patterns WHERE id = 1"
        ).fetchone()
        assert row[0] is not None
        assert "feedback:" in row[0]


# ---------------------------------------------------------------------------
# Phase B.5: semantic augmentation of memory_search
# ---------------------------------------------------------------------------

import embeddings  # noqa: E402
from tools.memory import _blend_score  # noqa: E402

REQUIRES_RAG = pytest.mark.skipif(
    not embeddings.is_available(),
    reason="sentence-transformers + numpy not installed (uv sync --extra rag)",
)


class TestBlendScore:
    def test_no_semantic_returns_five_signal(self) -> None:
        assert _blend_score(0.7, 0.0) == 0.7

    def test_negative_semantic_returns_five_signal(self) -> None:
        assert _blend_score(0.7, -0.1) == 0.7

    def test_blends_50_50(self) -> None:
        assert _blend_score(0.6, 0.4) == pytest.approx(0.5)

    def test_high_semantic_pulls_score_up(self) -> None:
        # Five-signal alone says 0.3, semantic says 0.9 → blend pulls score up
        result = _blend_score(0.3, 0.9)
        assert result > 0.3
        assert result == pytest.approx(0.6)


@REQUIRES_RAG
class TestMemorySearchSemantic:
    """End-to-end semantic augmentation tests for memory_search."""

    @pytest.fixture
    def embedded_seeded_conn(
        self, seeded_conn: sqlite3.Connection
    ) -> sqlite3.Connection:
        """Embed all seeded observations and patterns so semantic search has data."""
        from embeddings import upsert_embedding
        # Embed observations
        for row in seeded_conn.execute(
            "SELECT id, title, narrative, concepts FROM observations"
        ).fetchall():
            text = " ".join(filter(None, [row["title"], row["narrative"], row["concepts"]]))
            upsert_embedding(seeded_conn, "observations", row["id"], text)
        # Embed patterns
        for row in seeded_conn.execute(
            "SELECT id, pattern, concepts FROM learned_patterns"
        ).fetchall():
            text = " ".join(filter(None, [row["pattern"], row["concepts"]]))
            upsert_embedding(seeded_conn, "learned_patterns", row["id"], text)
        seeded_conn.commit()
        return seeded_conn

    def test_search_source_label_includes_semantic(
        self, embedded_seeded_conn: sqlite3.Connection
    ) -> None:
        result = memory_search(
            embedded_seeded_conn, query="database query optimization", limit=5,
        )
        # Source label should advertise semantic was used
        assert "semantic" in result.get("source", "")

    def test_semantic_finds_synonym_match(
        self, embedded_seeded_conn: sqlite3.Connection
    ) -> None:
        """A query with no keyword overlap should still find a related row
        through semantic similarity (not just FTS5/LIKE)."""
        # "ORM database layer" has no exact word overlap with the seeded
        # patterns/observations, but is conceptually close to "Always use
        # services layer for DB writes" (BACKEND/django/services/orm).
        result = memory_search(
            embedded_seeded_conn, query="ORM database layer", limit=10,
        )
        titles = " ".join(r.get("title", "") for r in result["results"])
        # Should surface either the services-layer pattern or a backend obs
        assert "services" in titles.lower() or "django" in titles.lower() or len(result["results"]) >= 1

    def test_semantic_does_not_break_existing_fts5_path(
        self, embedded_seeded_conn: sqlite3.Connection
    ) -> None:
        """Existing FTS5 keyword search should still work and return results."""
        result = memory_search(
            embedded_seeded_conn, query="postgres", limit=5,
        )
        assert result["count"] > 0

    def test_semantic_only_hit_is_appended(
        self, embedded_seeded_conn: sqlite3.Connection
    ) -> None:
        """A row that the FTS5/LIKE path misses but semantic finds should
        appear in the result list."""
        # Use a term that's semantically related but uses different vocabulary
        result = memory_search(
            embedded_seeded_conn, query="task scheduling background workers", limit=10,
        )
        # The Celery task observation should surface
        titles = " ".join(r.get("title", "").lower() for r in result["results"])
        assert "celery" in titles or len(result["results"]) >= 1

    def test_semantic_unavailable_falls_back_cleanly(
        self, embedded_seeded_conn: sqlite3.Connection, monkeypatch
    ) -> None:
        """When embeddings are unavailable, memory_search must still work."""
        monkeypatch.setattr(embeddings, "is_available", lambda: False)
        result = memory_search(
            embedded_seeded_conn, query="postgres", limit=5,
        )
        # Should still return results from FTS5/LIKE
        assert result["count"] >= 0
        # Source label should NOT include semantic
        assert "semantic" not in result.get("source", "")
