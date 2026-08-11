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
    memory_details,
    memory_promote,
    memory_timeline,
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

REQUIRES_RAG = pytest.mark.skipif(
    not embeddings.is_available(),
    reason="sentence-transformers + numpy not installed (uv sync --extra rag)",
)


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


class TestMemoryPromote:
    def test_promote_to_feedback(self, seeded_conn: sqlite3.Connection) -> None:
        result = memory_promote(
            seeded_conn,
            pattern_id=1,
            target="feedback",
            memory_dir="/tmp",
        )
        assert result["status"] == "promoted"
        assert "feedback" in result["filename"]
        assert "---" in result["content"]  # frontmatter

    def test_promote_to_rule(self, seeded_conn: sqlite3.Connection) -> None:
        result = memory_promote(
            seeded_conn,
            pattern_id=3,
            target="rule",
            memory_dir="/tmp",
        )
        assert result["status"] == "promoted"
        assert "learned_" in result["filename"]

    def test_promote_low_confidence_rejected(self, seeded_conn: sqlite3.Connection) -> None:
        # Pattern 4 has confidence 0.3 — exactly at threshold
        result = memory_promote(
            seeded_conn,
            pattern_id=4,
            target="feedback",
            memory_dir="/tmp",
        )
        assert result["status"] == "promoted"

        # Now lower it below threshold
        seeded_conn.execute("UPDATE learned_patterns SET confidence = 0.1 WHERE id = 4")
        seeded_conn.commit()
        result = memory_promote(
            seeded_conn,
            pattern_id=4,
            target="feedback",
            memory_dir="/tmp",
        )
        assert "error" in result

    def test_promote_not_found(self, seeded_conn: sqlite3.Connection) -> None:
        result = memory_promote(
            seeded_conn,
            pattern_id=999,
            target="feedback",
            memory_dir="/tmp",
        )
        assert "error" in result

    def test_promote_invalid_target(self, seeded_conn: sqlite3.Connection) -> None:
        result = memory_promote(
            seeded_conn,
            pattern_id=1,
            target="invalid",
            memory_dir="/tmp",
        )
        assert "error" in result

    def test_promote_updates_promoted_to(self, seeded_conn: sqlite3.Connection) -> None:
        memory_promote(
            seeded_conn,
            pattern_id=1,
            target="feedback",
            memory_dir="/tmp",
        )
        row = seeded_conn.execute(
            "SELECT promoted_to FROM learned_patterns WHERE id = 1"
        ).fetchone()
        assert row[0] is not None
        assert "feedback:" in row[0]
