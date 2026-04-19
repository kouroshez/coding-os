"""
Tests for core/thinking-os/tools/docs.py — Phase B.4 cos_doc_search.

Covers:
  - doc_search returns relevant chunks for semantic queries
  - source_type filter restricts results
  - dedupe_per_source caps chunks per file
  - priority boost ranks high-priority sources higher (when scores are close)
  - graceful degradation when embeddings unavailable
  - empty / missing inputs return empty list

End-to-end: tests build a small doc tree, run doc_indexer, then query via
doc_search to verify the full pipeline works.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Make the package importable from the package root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import embeddings  # noqa: E402
from db import init_db  # noqa: E402
from doc_indexer import index_docs  # noqa: E402
from tools.docs import doc_search  # noqa: E402

REQUIRES_RAG = pytest.mark.skipif(
    not embeddings.is_available(),
    reason="sentence-transformers + numpy not installed (uv sync --extra rag)",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_db(tmp_path: Path) -> sqlite3.Connection:
    conn = init_db(tmp_path / "test.db")
    yield conn
    conn.close()


@pytest.fixture
def indexed_project(tmp_path: Path, tmp_db: sqlite3.Connection) -> sqlite3.Connection:
    """Build a small docs/ tree, index it, return the connection.

    Doc set is intentionally small but covers multiple source types so
    filter and ranking tests can exercise real semantic distinctions.
    """
    project = tmp_path / "project"
    docs = project / "docs"
    (docs / "PRD").mkdir(parents=True)
    (docs / "architecture").mkdir(parents=True)
    (docs / "engineering").mkdir(parents=True)

    (docs / "PRD" / "01-vision.md").write_text(
        "<!-- domain:PRODUCT | layer:spec | ssot:true | updated:2026-04-06 -->\n"
        "# Vision\n\n"
        "## Authentication\n"
        "Users must be able to log in via JWT tokens with refresh support.\n\n"
        "## Payment\n"
        "Stripe integration handles all checkout flows.\n",
        encoding="utf-8",
    )

    (docs / "architecture" / "01-stack.md").write_text(
        "<!-- domain:ARCH | layer:spec | ssot:true | updated:2026-04-06 -->\n"
        "# Stack\n\n"
        "## Backend\n"
        "Django REST Framework with PostgreSQL database.\n\n"
        "## Frontend\n"
        "Next.js application with React components.\n",
        encoding="utf-8",
    )

    (docs / "engineering" / "auth-rules.md").write_text(
        "<!-- domain:BACKEND | layer:policy | ssot:true | updated:2026-04-06 -->\n"
        "# Authentication Rules\n\n"
        "## Token Storage\n"
        "Never store JWT tokens in localStorage. Use httpOnly cookies only.\n",
        encoding="utf-8",
    )

    state = project / ".coding-os"
    state.mkdir()
    config = state / "rag-config.yaml"
    config.write_text(
        """
sources:
  - path: docs/PRD/
    type: prd
  - path: docs/architecture/
    type: architecture
  - path: docs/engineering/
    type: engineering
    priority: 0.9

exclude: []
""",
        encoding="utf-8",
    )

    index_docs(tmp_db, config, project)
    return tmp_db


# ---------------------------------------------------------------------------
# Empty / unavailable cases
# ---------------------------------------------------------------------------

class TestDocSearchEdgeCases:
    def test_empty_query_returns_empty(self, tmp_db: sqlite3.Connection) -> None:
        assert doc_search(tmp_db, "") == []
        assert doc_search(tmp_db, "   ") == []

    def test_empty_db_returns_empty(self, tmp_db: sqlite3.Connection) -> None:
        # Migration v5 creates the tables but no chunks exist yet
        assert doc_search(tmp_db, "anything") == []

    def test_unavailable_returns_empty(self, tmp_db: sqlite3.Connection) -> None:
        with patch.object(embeddings, "is_available", return_value=False):
            assert doc_search(tmp_db, "any query") == []

    def test_missing_module_returns_empty(self, tmp_db: sqlite3.Connection) -> None:
        """When embeddings module fails to import → graceful empty result."""
        # Simulate by clearing the cached availability and patching is_available
        embeddings.is_available.cache_clear()
        with patch.object(embeddings, "is_available", return_value=False):
            results = doc_search(tmp_db, "test query")
            assert results == []


# ---------------------------------------------------------------------------
# Real semantic search (requires rag extras)
# ---------------------------------------------------------------------------

class TestDocSearchSemantic:
    @REQUIRES_RAG
    def test_finds_authentication_chunks(
        self, indexed_project: sqlite3.Connection
    ) -> None:
        """An auth query should surface the auth-related chunks across sources."""
        results = doc_search(indexed_project, "user login authentication", limit=5)
        assert len(results) >= 1
        # Inspect content for the strongest hit — should mention auth/JWT/login
        top_content = results[0]["content"].lower()
        assert any(
            keyword in top_content
            for keyword in ("jwt", "auth", "login", "token")
        )

    @REQUIRES_RAG
    def test_results_have_required_fields(
        self, indexed_project: sqlite3.Connection
    ) -> None:
        results = doc_search(indexed_project, "django backend", limit=3)
        assert len(results) >= 1
        required_keys = {
            "id", "source_path", "source_type", "heading_path",
            "content", "score", "cosine", "priority", "mtime", "chunk_index",
        }
        for result in results:
            assert required_keys.issubset(result.keys()), \
                f"missing keys: {required_keys - result.keys()}"

    @REQUIRES_RAG
    def test_results_sorted_by_score_desc(
        self, indexed_project: sqlite3.Connection
    ) -> None:
        results = doc_search(indexed_project, "stack technology", limit=5)
        scores = [r["score"] for r in results]
        assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# Source type filter
# ---------------------------------------------------------------------------

class TestDocSearchFiltering:
    @REQUIRES_RAG
    def test_source_type_filter_single(
        self, indexed_project: sqlite3.Connection
    ) -> None:
        results = doc_search(
            indexed_project,
            "authentication tokens",
            source_types=["prd"],
            limit=5,
        )
        assert all(r["source_type"] == "prd" for r in results)

    @REQUIRES_RAG
    def test_source_type_filter_multiple(
        self, indexed_project: sqlite3.Connection
    ) -> None:
        results = doc_search(
            indexed_project,
            "authentication",
            source_types=["prd", "engineering"],
            limit=5,
        )
        for r in results:
            assert r["source_type"] in {"prd", "engineering"}

    @REQUIRES_RAG
    def test_source_type_filter_empty_match(
        self, indexed_project: sqlite3.Connection
    ) -> None:
        """A filter that matches no rows should return empty list."""
        results = doc_search(
            indexed_project,
            "authentication",
            source_types=["nonexistent_type"],
            limit=5,
        )
        assert results == []


# ---------------------------------------------------------------------------
# Dedupe + limit
# ---------------------------------------------------------------------------

class TestDocSearchDedupe:
    @REQUIRES_RAG
    def test_dedupe_caps_chunks_per_source(
        self, indexed_project: sqlite3.Connection
    ) -> None:
        """Each source_path should appear at most twice when dedupe_per_source is True."""
        results = doc_search(
            indexed_project,
            "authentication",
            limit=20,
            dedupe_per_source=True,
        )
        per_source: dict[str, int] = {}
        for r in results:
            per_source[r["source_path"]] = per_source.get(r["source_path"], 0) + 1
        assert all(c <= 2 for c in per_source.values()), per_source

    @REQUIRES_RAG
    def test_no_dedupe_allows_all_chunks(
        self, indexed_project: sqlite3.Connection
    ) -> None:
        results = doc_search(
            indexed_project,
            "authentication",
            limit=20,
            dedupe_per_source=False,
        )
        # Without dedupe, we may see >2 chunks from a single source if that
        # source has many similar chunks. Just verify dedupe param is honored
        # by returning at least as many results as the deduped variant.
        deduped = doc_search(
            indexed_project,
            "authentication",
            limit=20,
            dedupe_per_source=True,
        )
        assert len(results) >= len(deduped)

    @REQUIRES_RAG
    def test_limit_respected(self, indexed_project: sqlite3.Connection) -> None:
        results = doc_search(indexed_project, "django", limit=2)
        assert len(results) <= 2


# ---------------------------------------------------------------------------
# Priority boost
# ---------------------------------------------------------------------------

class TestDocSearchPriority:
    @REQUIRES_RAG
    def test_engineering_priority_boost_present(
        self, indexed_project: sqlite3.Connection
    ) -> None:
        """Engineering source has priority=0.9, others use default 0.5.

        Verify the priority field is recorded on each result so callers can
        understand how scores were boosted.
        """
        results = doc_search(indexed_project, "JWT token storage rules", limit=5)
        eng_results = [r for r in results if r["source_type"] == "engineering"]
        assert len(eng_results) >= 1
        assert eng_results[0]["priority"] == pytest.approx(0.9)
        # Final score should be higher than raw cosine because of the boost
        assert eng_results[0]["score"] >= eng_results[0]["cosine"]
