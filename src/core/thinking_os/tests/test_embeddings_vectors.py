"""
Tests for core/thinking_os/embeddings.py — embeddings foundation.

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

import embeddings
from database import init_db

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


class TestEmbedText:
    @REQUIRES_RAG
    def test_embed_text_returns_correct_size(self) -> None:
        result = embeddings.embed_text("hello world")
        assert result is not None
        assert isinstance(result, bytes)
        # Size tracks the active model's dim (MiniLM 384 / BGE-M3 1024), float32.
        expected_bytes = embeddings.model_dim(embeddings.active_model_name()) * 4
        assert len(result) == expected_bytes

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
        expected_bytes = embeddings.model_dim(embeddings.active_model_name()) * 4
        assert all(r is not None and len(r) == expected_bytes for r in results)

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
    @pytest.mark.real_embeddings
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


class TestTextHash:
    def test_hash_length_16(self) -> None:
        h = embeddings._compute_text_hash("any text")
        assert len(h) == 16

    def test_hash_deterministic(self) -> None:
        assert embeddings._compute_text_hash("same") == embeddings._compute_text_hash("same")

    def test_hash_different_inputs_differ(self) -> None:
        assert embeddings._compute_text_hash("a") != embeddings._compute_text_hash("b")


class TestMemorySimilarityFloor:
    def test_bge_m3_floor(self) -> None:
        assert embeddings.memory_similarity_floor("BAAI/bge-m3") == 0.45

    def test_unknown_model_falls_back_to_legacy(self) -> None:
        assert embeddings.memory_similarity_floor("some-unknown-model") == 0.05
