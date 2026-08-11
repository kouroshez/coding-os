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
from tools._learning_narrative import learn_narrative
from tools._learning_store import _upsert_pattern

REQUIRES_RAG = pytest.mark.skipif(
    not embeddings.is_available(),
    reason="sentence-transformers + numpy not installed (uv sync --extra rag)",
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
