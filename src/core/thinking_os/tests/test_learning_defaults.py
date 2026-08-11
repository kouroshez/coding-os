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
from tools._learning_store import _upsert_pattern

REQUIRES_RAG = pytest.mark.skipif(
    not embeddings.is_available(),
    reason="sentence-transformers + numpy not installed (uv sync --extra rag)",
)


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
