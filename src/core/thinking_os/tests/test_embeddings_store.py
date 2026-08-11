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
        with (
            patch.object(embeddings, "is_available", return_value=True),
            patch.object(embeddings, "_get_model", return_value=None),
            patch.object(embeddings, "embed_text", return_value=None),
        ):
            result = embeddings.upsert_embedding(tmp_db, "observations", 1, "text")
            assert result["status"] in ("skipped",)


class TestHasEmbeddingsData:
    def test_empty_db_returns_false(self, tmp_db: sqlite3.Connection) -> None:
        # Migration v5 creates the table but it has no rows initially
        assert embeddings.has_embeddings_data(tmp_db) is False

    @REQUIRES_RAG
    def test_returns_true_after_insert(self, tmp_db: sqlite3.Connection) -> None:
        embeddings.upsert_embedding(tmp_db, "observations", 1, "anything")
        assert embeddings.has_embeddings_data(tmp_db) is True


class TestSearchSimilar:
    @REQUIRES_RAG
    @pytest.mark.real_embeddings
    def test_finds_synonym(self, tmp_db: sqlite3.Connection) -> None:
        """The whole point of RAG: 'authentication problem' should rank a JWT
        observation above an unrelated color one. all-MiniLM-L6-v2 produces
        modest absolute scores on short text (~0.1-0.3 for related, <0.1 for
        unrelated), so we lower the threshold and assert ranking, not score.
        """
        embeddings.upsert_embedding(
            tmp_db,
            "learned_patterns",
            1,
            "JWT token refresh failing in production",
        )
        embeddings.upsert_embedding(
            tmp_db,
            "learned_patterns",
            2,
            "color palette tokens for dark mode",
        )
        results = embeddings.search_similar(
            tmp_db,
            "authentication problem",
            limit=5,
            threshold=0.05,
        )
        assert len(results) >= 1
        # Auth-related row must rank first
        assert results[0]["source_id"] == 1
        # And it must outscore the unrelated color row
        if len(results) > 1:
            assert results[0]["score"] > results[1]["score"]

    @REQUIRES_RAG
    def test_threshold_filters_low_scores(self, tmp_db: sqlite3.Connection) -> None:
        embeddings.upsert_embedding(
            tmp_db, "observations", 1, "completely unrelated topic about cooking"
        )
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

    @REQUIRES_RAG
    def test_dual_model_bridge_surfaces_both_dims(self, tmp_db: sqlite3.Connection) -> None:
        # Wave 2 (M4): mid-migration the table holds vectors from two models
        # at different dims. search_similar must encode the query with EVERY
        # present model and surface rows from BOTH — the old single-model path
        # silently dropped the other-dim cohort (dim_mismatch → score 0).
        import numpy as np

        def _const_encoder(dim: int):
            class _E:
                def encode(self, text, **kw):
                    v = np.ones(dim, dtype=np.float32)
                    return v / np.linalg.norm(v)

            return _E()

        def _blob(dim: int) -> bytes:
            v = np.ones(dim, dtype=np.float32)
            return (v / np.linalg.norm(v)).astype(np.float32).tobytes()

        embeddings._override_model("m-a", _const_encoder(4))
        embeddings._override_model("m-b", _const_encoder(6))
        try:
            tmp_db.execute(
                "INSERT INTO embeddings (source_table, source_id, text_hash, "
                "embedding, model_name, embedding_dim) VALUES "
                "('observations', 1, 'h1', ?, 'm-a', 4)",
                (_blob(4),),
            )
            tmp_db.execute(
                "INSERT INTO embeddings (source_table, source_id, text_hash, "
                "embedding, model_name, embedding_dim) VALUES "
                "('observations', 2, 'h2', ?, 'm-b', 6)",
                (_blob(6),),
            )
            tmp_db.commit()
            hits = embeddings.search_similar(
                tmp_db, "q", source_tables=["observations"], limit=10, threshold=0.5
            )
            ids = {h["source_id"] for h in hits}
            assert ids == {1, 2}, f"both model cohorts must surface, got {ids}"
        finally:
            embeddings._override_model("m-a", None)
            embeddings._override_model("m-b", None)


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

    @REQUIRES_RAG
    def test_reindex_embeds_allowlisted_graph_nodes_only(self, tmp_db: sqlite3.Connection) -> None:
        # Wave 1: reindex_all must embed meaningful graph_node kinds and skip
        # noise kinds (identifier/import_/module) that pollute similarity.
        now = 0
        rows = [
            ("function", "embed_text", "def embed_text(text)", "Embed one string."),
            ("class", "SqliteBackend", "class SqliteBackend", "Graph storage backend."),
            ("mcp_tool", "cos_graph_query", "def cos_graph_query(q)", "Query the graph."),
            ("identifier", "unresolved:str", None, None),  # must be SKIPPED
            ("import_", "os", None, None),  # must be SKIPPED
        ]
        for _i, (kind, label, sig, doc) in enumerate(rows, start=1):
            tmp_db.execute(
                "INSERT INTO graph_nodes (kind, label, uid, signature, doc_blob, "
                "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (kind, label, f"code:{kind}:t.py::{label}", sig, doc, now, now),
            )
        tmp_db.commit()

        report = embeddings.reindex_all(tmp_db)

        assert report["graph_nodes"]["processed"] == 3  # only allowlisted kinds
        assert report["graph_nodes"]["inserted"] == 3
        embedded_kinds = {
            r[0]
            for r in tmp_db.execute(
                "SELECT n.kind FROM embeddings e JOIN graph_nodes n "
                "ON n.id = e.source_id WHERE e.source_table = 'graph_nodes'"
            ).fetchall()
        }
        assert embedded_kinds == {"function", "class", "mcp_tool"}
