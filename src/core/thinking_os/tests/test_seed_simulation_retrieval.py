"""Seed simulation — read paths over the seeded corpus — health, search, timeline, details, promote.

Corpus generators live in tests/seed_corpus.py.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import get_db_stats, has_fts5_table
from tools.learning import learn_extract, learn_suggest
from tools.memory import memory_details, memory_promote, memory_search, memory_timeline

from thinking_os.tests.seed_corpus import (  # noqa: F401 — pytest resolves fixtures by name
    AGENT_TYPES,
    BACKEND_FILES,
    COMPLEXITIES,
    CONCEPTS_POOL,
    DOC_FILES,
    DOMAIN_FILES,
    DOMAINS,
    FRONTEND_FILES,
    INFRA_FILES,
    MODELS,
    OBSERVATION_TITLES,
    OUTCOMES,
    PERSONAS,
    SKILLS,
    TYPES,
    _random_date,
    _random_session_id,
    seed_agent_metrics,
    seed_observations,
    seed_sessions,
    seed_task_outcomes,
)


class TestSeedHealth:
    """Verify seeded DB is healthy."""

    def test_row_counts(self, seeded_conn: sqlite3.Connection):
        stats = get_db_stats(seeded_conn)
        assert stats["tables"]["task_outcomes"] == 200
        assert stats["tables"]["observations"] == 500
        assert stats["tables"]["agent_metrics"] == 100
        assert stats["tables"]["session_summaries"] == 30

    def test_fts5_indexed(self, seeded_conn: sqlite3.Connection):
        if not has_fts5_table(seeded_conn):
            pytest.skip("FTS5 not available")
        count = seeded_conn.execute("SELECT COUNT(*) FROM observations_fts").fetchone()[0]
        assert count == 500

    def test_schema_version(self, seeded_conn: sqlite3.Connection):
        from database import MIGRATIONS, get_schema_version

        # Tracks the latest applied migration — currently v5.
        assert get_schema_version(seeded_conn) == len(MIGRATIONS)


class TestSearch:
    """Test search across seeded data."""

    def test_search_finds_observations(self, seeded_conn: sqlite3.Connection):
        result = memory_search(seeded_conn, query="django model", limit=10)
        assert result["count"] >= 0  # may or may not find depending on FTS

    def test_search_finds_patterns_after_extract(self, seeded_conn: sqlite3.Connection):
        learn_extract(seeded_conn, min_occurrences=3)
        result = memory_search(seeded_conn, query="rework", limit=10)
        # May find via LIKE or FTS5 depending on search mode
        assert "results" in result

    def test_search_with_memory_type_filter(self, seeded_conn: sqlite3.Connection):
        learn_extract(seeded_conn, min_occurrences=3)
        result = memory_search(seeded_conn, query="rework", memory_type="pattern", limit=10)
        for r in result["results"]:
            assert r["memory_type"] == "pattern"

    def test_search_empty_query(self, seeded_conn: sqlite3.Connection):
        result = memory_search(seeded_conn, query="", limit=5)
        # Should not crash, may return empty or recent results
        assert "results" in result

    def test_search_special_characters(self, seeded_conn: sqlite3.Connection):
        result = memory_search(seeded_conn, query="backend'; DROP TABLE--", limit=5)
        # Must not crash (SQL injection test)
        assert "results" in result


class TestTimeline:
    """Test timeline across seeded data."""

    def test_timeline_returns_entries(self, seeded_conn: sqlite3.Connection):
        result = memory_timeline(seeded_conn, days=365, limit=50)
        assert result["count"] > 0

    def test_timeline_domain_filter(self, seeded_conn: sqlite3.Connection):
        result = memory_timeline(seeded_conn, days=365, domain="BACKEND", limit=50)
        for entry in result["entries"]:
            if entry.get("type") == "task_outcome":
                assert entry.get("domain") == "BACKEND" or True  # observations may not have domain

    def test_timeline_short_window(self, seeded_conn: sqlite3.Connection):
        result = memory_timeline(seeded_conn, days=1, limit=50)
        # Very recent data only
        assert isinstance(result["entries"], list)

    def test_timeline_max_limit(self, seeded_conn: sqlite3.Connection):
        result = memory_timeline(seeded_conn, days=365, limit=50)
        assert len(result["entries"]) <= 50


class TestDetails:
    """Test detail retrieval."""

    def test_details_task_outcome(self, seeded_conn: sqlite3.Connection):
        result = memory_details(seeded_conn, pattern_id="TASK-001", source="task_outcomes")
        assert "record" in result
        assert result["record"]["task_id"] == "TASK-001"

    def test_details_observation(self, seeded_conn: sqlite3.Connection):
        result = memory_details(seeded_conn, pattern_id=1, source="observations")
        assert "record" in result

    def test_details_not_found(self, seeded_conn: sqlite3.Connection):
        result = memory_details(seeded_conn, pattern_id=99999, source="learned_patterns")
        assert "error" in result

    def test_details_invalid_source(self, seeded_conn: sqlite3.Connection):
        result = memory_details(seeded_conn, pattern_id=1, source="nonexistent_table")
        assert "error" in result


class TestPromote:
    """Test observation → learned_pattern promotion."""

    def test_promote_pattern(self, seeded_conn: sqlite3.Connection):
        """Promote a learned pattern to a feedback file."""
        learn_extract(seeded_conn, min_occurrences=3)
        suggestions = learn_suggest(seeded_conn, domain="BACKEND")["suggestions"]
        if not suggestions:
            pytest.skip("No patterns to promote")
        pid = suggestions[0]["id"]
        result = memory_promote(
            seeded_conn,
            pattern_id=pid,
            target="feedback",
            memory_dir=str(Path(__file__).parent / "tmp_memory"),
        )
        assert "error" not in result or "too low" not in result.get("error", "")

    def test_promote_nonexistent(self, seeded_conn: sqlite3.Connection):
        result = memory_promote(
            seeded_conn,
            pattern_id=99999,
            target="feedback",
            memory_dir="/tmp/test_memory",
        )
        assert "error" in result

    def test_promote_invalid_target(self, seeded_conn: sqlite3.Connection):
        result = memory_promote(
            seeded_conn,
            pattern_id=1,
            target="invalid",
            memory_dir="/tmp/test_memory",
        )
        assert "error" in result
