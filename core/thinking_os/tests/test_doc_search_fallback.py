"""
Tests for docs.py G.7.3 additions — mode routing, identifier detection,
FTS5 fallback, LIKE last-resort.

Independent from `test_doc_search.py` so the existing semantic-path tests
stay unchanged.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import has_document_chunks_fts, has_fts5, init_db  # noqa: E402
from tools.docs import doc_search, looks_like_identifier  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_db(tmp_path: Path) -> sqlite3.Connection:
    conn = init_db(tmp_path / "test.db")
    yield conn
    conn.close()


def _insert_chunk(
    conn: sqlite3.Connection,
    *,
    path: str,
    source_type: str,
    heading: str,
    content: str,
    chunk_index: int = 0,
    priority: float = 0.5,
) -> int:
    cur = conn.execute(
        "INSERT INTO document_chunks "
        "(source_path, source_type, chunk_index, heading_path, content, "
        "content_hash, priority, mtime) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (path, source_type, chunk_index, heading, content,
         f"h{chunk_index}", priority, 1),
    )
    conn.commit()
    return cur.lastrowid


# ---------------------------------------------------------------------------
# looks_like_identifier heuristic
# ---------------------------------------------------------------------------

class TestIdentifierHeuristic:
    @pytest.mark.parametrize("query", [
        "upsert_embedding",
        "doc_search()",
        "MemoryAudit",
        "TASK-199",
        "`cos_doc_search`",
        "doc_indexer.py",
        "memory.ts",
    ])
    def test_positive(self, query: str) -> None:
        assert looks_like_identifier(query) is True

    @pytest.mark.parametrize("query", [
        "how does money handling work",
        "auth flow diagram",
        "commission rate calculation",
        "",
        "   ",
        "single",
        "two words",
    ])
    def test_negative(self, query: str) -> None:
        assert looks_like_identifier(query) is False


# ---------------------------------------------------------------------------
# mode="lexical" — FTS5 path (skips gracefully without FTS5)
# ---------------------------------------------------------------------------

class TestLexicalMode:
    def test_returns_fts_hit_marked_lexical(self, tmp_db: sqlite3.Connection) -> None:
        if not has_fts5(tmp_db) or not has_document_chunks_fts(tmp_db):
            pytest.skip("FTS5 not available")
        _insert_chunk(
            tmp_db,
            path="docs/engineering/db.md",
            source_type="engineering",
            heading="Database > Embeddings",
            content="The upsert_embedding helper performs a safe upsert.",
        )

        results = doc_search(tmp_db, query="upsert_embedding", mode="lexical", limit=5)
        assert len(results) >= 1
        assert results[0]["retrieval_source"] == "lexical"
        assert "upsert_embedding" in results[0]["content"]

    def test_lexical_filters_by_source_type(self, tmp_db: sqlite3.Connection) -> None:
        if not has_fts5(tmp_db) or not has_document_chunks_fts(tmp_db):
            pytest.skip("FTS5 not available")
        _insert_chunk(tmp_db, path="docs/prd/a.md", source_type="prd",
                      heading="PRD", content="mentions upsert_embedding")
        _insert_chunk(tmp_db, path="docs/eng/a.md", source_type="engineering",
                      heading="Eng", content="also mentions upsert_embedding")

        results = doc_search(
            tmp_db, query="upsert_embedding", mode="lexical",
            source_types=["engineering"], limit=5,
        )
        assert all(r["source_type"] == "engineering" for r in results)

    def test_lexical_empty_query_returns_empty(self, tmp_db: sqlite3.Connection) -> None:
        assert doc_search(tmp_db, query="", mode="lexical") == []


# ---------------------------------------------------------------------------
# mode="auto" — routing semantics
# ---------------------------------------------------------------------------

class TestAutoMode:
    def test_identifier_query_prefers_lexical(self, tmp_db: sqlite3.Connection) -> None:
        """Auto + identifier query = FTS first. Forcing no-embedding should
        still yield the FTS hit."""
        if not has_fts5(tmp_db) or not has_document_chunks_fts(tmp_db):
            pytest.skip("FTS5 not available")
        _insert_chunk(
            tmp_db, path="docs/x.md", source_type="engineering",
            heading="X", content="upsert_embedding is in the code",
        )

        with patch("embeddings.is_available", return_value=False):
            results = doc_search(tmp_db, query="upsert_embedding", mode="auto", limit=5)
        assert len(results) >= 1
        assert results[0]["retrieval_source"] in ("lexical", "lexical-like")

    def test_conceptual_query_falls_back_to_lexical_when_semantic_empty(
        self, tmp_db: sqlite3.Connection
    ) -> None:
        """Conceptual query + embeddings unavailable → should still return
        something via lexical/LIKE path instead of [] (old contract)."""
        _insert_chunk(
            tmp_db, path="docs/money.md", source_type="engineering",
            heading="Money", content="money handling uses Decimal",
        )

        with patch("embeddings.is_available", return_value=False):
            results = doc_search(
                tmp_db, query="money handling", mode="auto", limit=5,
            )
        # Fallback must surface the chunk even without embeddings.
        assert len(results) >= 1
        assert "money" in results[0]["content"].lower()


# ---------------------------------------------------------------------------
# mode="semantic" — legacy path, no fallback
# ---------------------------------------------------------------------------

class TestSemanticModeStrict:
    def test_returns_empty_when_embeddings_unavailable(
        self, tmp_db: sqlite3.Connection
    ) -> None:
        _insert_chunk(tmp_db, path="docs/x.md", source_type="engineering",
                      heading="X", content="irrelevant")

        with patch("embeddings.is_available", return_value=False):
            results = doc_search(tmp_db, query="money handling",
                                 mode="semantic", limit=5)
        assert results == []


# ---------------------------------------------------------------------------
# Dedupe still works across modes
# ---------------------------------------------------------------------------

class TestDedupeAcrossModes:
    def test_dedupe_caps_lexical_results_per_source(
        self, tmp_db: sqlite3.Connection
    ) -> None:
        if not has_fts5(tmp_db) or not has_document_chunks_fts(tmp_db):
            pytest.skip("FTS5 not available")
        # Insert 5 chunks from the same file all matching "widget"
        for i in range(5):
            _insert_chunk(
                tmp_db, path="docs/same.md", source_type="engineering",
                heading=f"H{i}", content="widget docs",
                chunk_index=i,
            )

        results = doc_search(tmp_db, query="widget", mode="lexical",
                             dedupe_per_source=True, limit=10)
        paths = [r["source_path"] for r in results]
        assert paths.count("docs/same.md") <= 2  # capped at _MAX_PER_SOURCE
