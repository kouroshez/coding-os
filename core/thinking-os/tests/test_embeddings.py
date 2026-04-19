"""
Tests for core/thinking-os/embeddings.py — Phase B foundation.

Covers:
  - is_available() detection (installed vs not)
  - embed_text / embed_texts (size, batch, empty input)
  - cosine_similarity (identical, orthogonal, malformed inputs)
  - upsert_embedding (insert, update, unchanged, missing table)
  - search_similar (basic match, threshold, source_table filter, semantic synonym)
  - has_embeddings_data
  - reindex_all
  - graceful degradation when sentence-transformers is unavailable

Tests that require the real embedding model are marked with
`@pytest.mark.skipif(not embeddings.is_available(), ...)`. Pure unit tests
that exercise the graceful-degradation path run unconditionally.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Make `embeddings` and `db` importable from the package root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import embeddings  # noqa: E402
from db import init_db  # noqa: E402

REQUIRES_RAG = pytest.mark.skipif(
    not embeddings.is_available(),
    reason="sentence-transformers + numpy not installed (uv sync --extra rag)",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_db(tmp_path: Path) -> sqlite3.Connection:
    """Return a fully migrated SQLite connection on a temp DB."""
    conn = init_db(tmp_path / "test.db")
    yield conn
    conn.close()


@pytest.fixture(autouse=True)
def _clear_lru_cache():
    """Clear cached _get_model and is_available results between tests so
    monkeypatching imports works reliably."""
    embeddings._get_model.cache_clear()
    embeddings.is_available.cache_clear()
    yield
    embeddings._get_model.cache_clear()
    embeddings.is_available.cache_clear()


# ---------------------------------------------------------------------------
# Availability detection
# ---------------------------------------------------------------------------

class TestAvailability:
    def test_is_available_returns_bool(self) -> None:
        result = embeddings.is_available()
        assert isinstance(result, bool)

    def test_is_available_caches_result(self) -> None:
        # Call twice — should return same value with no exceptions
        first = embeddings.is_available()
        second = embeddings.is_available()
        assert first == second

    def test_is_available_false_when_module_missing(self) -> None:
        """Simulate ImportError → is_available returns False."""
        embeddings.is_available.cache_clear()
        with patch.dict(sys.modules, {"sentence_transformers": None}):
            assert embeddings.is_available() is False


# ---------------------------------------------------------------------------
# embed_text / embed_texts
# ---------------------------------------------------------------------------

class TestEmbedText:
    @REQUIRES_RAG
    def test_embed_text_returns_correct_size(self) -> None:
        result = embeddings.embed_text("hello world")
        assert result is not None
        assert isinstance(result, bytes)
        assert len(result) == embeddings.EMBEDDING_BYTES  # 1536 bytes

    @REQUIRES_RAG
    def test_embed_text_deterministic(self) -> None:
        first = embeddings.embed_text("the same input")
        second = embeddings.embed_text("the same input")
        assert first == second

    @REQUIRES_RAG
    def test_embed_text_different_inputs_differ(self) -> None:
        a = embeddings.embed_text("authentication failure")
        b = embeddings.embed_text("color theme tokens")
        assert a != b

    def test_embed_text_empty_returns_none(self) -> None:
        assert embeddings.embed_text("") is None
        assert embeddings.embed_text("   ") is None

    def test_embed_text_graceful_when_unavailable(self) -> None:
        """When the model fails to load, embed_text returns None safely."""
        embeddings._get_model.cache_clear()
        with patch.object(embeddings, "_get_model", return_value=None):
            assert embeddings.embed_text("anything") is None


class TestEmbedTexts:
    @REQUIRES_RAG
    def test_embed_texts_batch(self) -> None:
        results = embeddings.embed_texts(["one", "two", "three"])
        assert len(results) == 3
        assert all(r is not None and len(r) == embeddings.EMBEDDING_BYTES for r in results)

    @REQUIRES_RAG
    def test_embed_texts_handles_empty_entries(self) -> None:
        results = embeddings.embed_texts(["valid", "", "  ", "also valid"])
        assert results[0] is not None
        assert results[1] is None
        assert results[2] is None
        assert results[3] is not None

    def test_embed_texts_empty_list(self) -> None:
        assert embeddings.embed_texts([]) == []

    def test_embed_texts_graceful_when_unavailable(self) -> None:
        embeddings._get_model.cache_clear()
        with patch.object(embeddings, "_get_model", return_value=None):
            results = embeddings.embed_texts(["a", "b", "c"])
            assert results == [None, None, None]


# ---------------------------------------------------------------------------
# cosine_similarity
# ---------------------------------------------------------------------------

class TestCosineSimilarity:
    @REQUIRES_RAG
    def test_identical_vectors_score_one(self) -> None:
        vec = embeddings.embed_text("identity")
        scores = embeddings.cosine_similarity(vec, [vec])
        assert len(scores) == 1
        assert scores[0] == pytest.approx(1.0, abs=1e-5)

    @REQUIRES_RAG
    def test_unrelated_vectors_score_below_one(self) -> None:
        a = embeddings.embed_text("python programming language")
        b = embeddings.embed_text("the color purple at sunset")
        scores = embeddings.cosine_similarity(a, [b])
        assert len(scores) == 1
        assert scores[0] < 0.7  # they should not be near-identical

    @REQUIRES_RAG
    def test_batch_returns_score_per_candidate(self) -> None:
        query = embeddings.embed_text("authentication")
        candidates = [
            embeddings.embed_text("login flow"),
            embeddings.embed_text("user permission"),
            embeddings.embed_text("color palette"),
        ]
        scores = embeddings.cosine_similarity(query, candidates)
        assert len(scores) == 3
        # Auth-related should score higher than color
        assert scores[0] > scores[2]
        assert scores[1] > scores[2]

    def test_empty_query_returns_empty(self) -> None:
        assert embeddings.cosine_similarity(b"", [b"x" * embeddings.EMBEDDING_BYTES]) == []

    def test_empty_candidates_returns_empty(self) -> None:
        assert embeddings.cosine_similarity(b"x" * embeddings.EMBEDDING_BYTES, []) == []

    @REQUIRES_RAG
    def test_malformed_candidate_yields_zero(self) -> None:
        """A candidate with wrong byte length should not crash — it should score 0."""
        query = embeddings.embed_text("hello")
        scores = embeddings.cosine_similarity(query, [b"too-short"])
        assert scores == [0.0]


# ---------------------------------------------------------------------------
# upsert_embedding
# ---------------------------------------------------------------------------

class TestUpsertEmbedding:
    @REQUIRES_RAG
    def test_insert_creates_row(self, tmp_db: sqlite3.Connection) -> None:
        result = embeddings.upsert_embedding(tmp_db, "observations", 1, "first text")
        assert result["status"] == "inserted"
        row = tmp_db.execute(
            "SELECT source_table, source_id, text_hash FROM embeddings WHERE id = ?",
            (result["id"],),
        ).fetchone()
        assert row[0] == "observations"
        assert row[1] == 1
        assert len(row[2]) == 16  # 16-char SHA256 prefix

    @REQUIRES_RAG
    def test_unchanged_text_skips_write(self, tmp_db: sqlite3.Connection) -> None:
        embeddings.upsert_embedding(tmp_db, "observations", 1, "stable text")
        second = embeddings.upsert_embedding(tmp_db, "observations", 1, "stable text")
        assert second["status"] == "unchanged"

    @REQUIRES_RAG
    def test_changed_text_updates_row(self, tmp_db: sqlite3.Connection) -> None:
        first = embeddings.upsert_embedding(tmp_db, "observations", 1, "old text")
        second = embeddings.upsert_embedding(tmp_db, "observations", 1, "new text")
        assert second["status"] == "updated"
        # Same DB row id reused
        assert second["id"] == first["id"]

    def test_empty_text_skipped(self, tmp_db: sqlite3.Connection) -> None:
        # Mock is_available so the 'empty_text' branch is reachable even
        # when the rag extras aren't installed in this test environment.
        embeddings.is_available.cache_clear()
        with patch.object(embeddings, "is_available", return_value=True):
            result = embeddings.upsert_embedding(tmp_db, "observations", 1, "")
        assert result["status"] == "skipped"
        assert result["reason"] == "empty_text"

    def test_unavailable_skipped(self, tmp_db: sqlite3.Connection) -> None:
        embeddings.is_available.cache_clear()
        with patch.object(embeddings, "is_available", return_value=True):
            with patch.object(embeddings, "_get_model", return_value=None):
                with patch.object(embeddings, "embed_text", return_value=None):
                    result = embeddings.upsert_embedding(tmp_db, "observations", 1, "text")
                    assert result["status"] in ("skipped",)


# ---------------------------------------------------------------------------
# has_embeddings_data
# ---------------------------------------------------------------------------

class TestHasEmbeddingsData:
    def test_empty_db_returns_false(self, tmp_db: sqlite3.Connection) -> None:
        # Migration v5 creates the table but it has no rows initially
        assert embeddings.has_embeddings_data(tmp_db) is False

    @REQUIRES_RAG
    def test_returns_true_after_insert(self, tmp_db: sqlite3.Connection) -> None:
        embeddings.upsert_embedding(tmp_db, "observations", 1, "anything")
        assert embeddings.has_embeddings_data(tmp_db) is True


# ---------------------------------------------------------------------------
# search_similar
# ---------------------------------------------------------------------------

class TestSearchSimilar:
    @REQUIRES_RAG
    def test_finds_synonym(self, tmp_db: sqlite3.Connection) -> None:
        """The whole point of RAG: 'authentication problem' should rank a JWT
        observation above an unrelated color one. all-MiniLM-L6-v2 produces
        modest absolute scores on short text (~0.1-0.3 for related, <0.1 for
        unrelated), so we lower the threshold and assert ranking, not score.
        """
        embeddings.upsert_embedding(
            tmp_db, "learned_patterns", 1, "JWT token refresh failing in production",
        )
        embeddings.upsert_embedding(
            tmp_db, "learned_patterns", 2, "color palette tokens for dark mode",
        )
        results = embeddings.search_similar(
            tmp_db, "authentication problem", limit=5, threshold=0.05,
        )
        assert len(results) >= 1
        # Auth-related row must rank first
        assert results[0]["source_id"] == 1
        # And it must outscore the unrelated color row
        if len(results) > 1:
            assert results[0]["score"] > results[1]["score"]

    @REQUIRES_RAG
    def test_threshold_filters_low_scores(self, tmp_db: sqlite3.Connection) -> None:
        embeddings.upsert_embedding(tmp_db, "observations", 1, "completely unrelated topic about cooking")
        results = embeddings.search_similar(
            tmp_db,
            query="quantum physics",
            limit=5,
            threshold=0.95,  # impossibly high
        )
        assert results == []

    @REQUIRES_RAG
    def test_source_table_filter(self, tmp_db: sqlite3.Connection) -> None:
        embeddings.upsert_embedding(tmp_db, "observations", 1, "auth flow")
        embeddings.upsert_embedding(tmp_db, "learned_patterns", 1, "auth flow")
        results = embeddings.search_similar(
            tmp_db,
            query="auth flow",
            source_tables=["learned_patterns"],
            limit=5,
        )
        assert all(r["source_table"] == "learned_patterns" for r in results)

    def test_empty_query_returns_empty(self, tmp_db: sqlite3.Connection) -> None:
        assert embeddings.search_similar(tmp_db, "") == []
        assert embeddings.search_similar(tmp_db, "   ") == []

    def test_empty_table_returns_empty(self, tmp_db: sqlite3.Connection) -> None:
        # Table exists (migration v5) but no rows
        assert embeddings.search_similar(tmp_db, "anything") == []

    def test_unavailable_returns_empty(self, tmp_db: sqlite3.Connection) -> None:
        with patch.object(embeddings, "is_available", return_value=False):
            assert embeddings.search_similar(tmp_db, "anything") == []


# ---------------------------------------------------------------------------
# reindex_all
# ---------------------------------------------------------------------------

class TestReindexAll:
    @REQUIRES_RAG
    def test_reindex_picks_up_existing_observations(self, tmp_db: sqlite3.Connection) -> None:
        # Insert an observation directly without an embedding
        tmp_db.execute(
            "INSERT INTO observations (title, narrative, concepts) VALUES (?, ?, ?)",
            ("Login bug", "JWT token refresh failing", '["auth","jwt"]'),
        )
        tmp_db.commit()

        report = embeddings.reindex_all(tmp_db)
        assert isinstance(report, dict)
        assert report["observations"]["processed"] == 1
        assert report["observations"]["inserted"] == 1

    def test_reindex_unavailable_returns_skipped(self, tmp_db: sqlite3.Connection) -> None:
        with patch.object(embeddings, "is_available", return_value=False):
            result = embeddings.reindex_all(tmp_db)
            assert result.get("status") == "skipped"


# ---------------------------------------------------------------------------
# Text hash helper
# ---------------------------------------------------------------------------

class TestTextHash:
    def test_hash_length_16(self) -> None:
        h = embeddings._compute_text_hash("any text")
        assert len(h) == 16

    def test_hash_deterministic(self) -> None:
        assert embeddings._compute_text_hash("same") == embeddings._compute_text_hash("same")

    def test_hash_different_inputs_differ(self) -> None:
        assert embeddings._compute_text_hash("a") != embeddings._compute_text_hash("b")
