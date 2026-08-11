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
    learn_extract,
    learn_suggest,
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
