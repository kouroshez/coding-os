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

    def test_fts5_indexed(self, seeded_conn: sqlite3.Connection):
        if not has_fts5_table(seeded_conn):
            pytest.skip("FTS5 not available")
        count = seeded_conn.execute("SELECT COUNT(*) FROM observations_fts").fetchone()[0]
        assert count == 500

    def test_schema_version(self, seeded_conn: sqlite3.Connection):
        from database import MIGRATIONS, get_schema_version

        # Tracks the latest applied migration — currently v5.
        assert get_schema_version(seeded_conn) == len(MIGRATIONS)
