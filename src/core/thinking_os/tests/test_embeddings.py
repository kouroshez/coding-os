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
    def test_dual_model_bridge_surfaces_both_dims(
        self, tmp_db: sqlite3.Connection
    ) -> None:
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

    @REQUIRES_RAG
    def test_reindex_embeds_allowlisted_graph_nodes_only(
        self, tmp_db: sqlite3.Connection
    ) -> None:
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
        for i, (kind, label, sig, doc) in enumerate(rows, start=1):
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


# ---------------------------------------------------------------------------
# Text hash helper
# ---------------------------------------------------------------------------


class TestModelSSOTAndCutover:
    """Wave 2 (M5 + cutover gate): single source of truth for the active model
    and a gate that reports re-embedding completeness before a default flip."""

    def test_env_wins_over_marker(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("COS_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("COS_EMBEDDING_MODEL", "BAAI/bge-m3")
        embeddings.set_active_model("all-MiniLM-L6-v2")  # marker says MiniLM
        assert embeddings.active_model_name() == "BAAI/bge-m3"  # env still wins

    def test_marker_used_when_env_absent(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("COS_STATE_DIR", str(tmp_path))
        monkeypatch.delenv("COS_EMBEDDING_MODEL", raising=False)
        embeddings.set_active_model("BAAI/bge-m3")
        assert embeddings.active_model_name() == "BAAI/bge-m3"

    def test_default_when_neither_set(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("COS_STATE_DIR", str(tmp_path))
        monkeypatch.delenv("COS_EMBEDDING_MODEL", raising=False)
        assert embeddings.active_model_name() == embeddings.DEFAULT_MODEL_NAME

    def test_set_active_model_rejects_unknown(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("COS_STATE_DIR", str(tmp_path))
        with pytest.raises(ValueError):
            embeddings.set_active_model("not-a-real-model")

    def test_floor_is_model_calibrated(self) -> None:
        assert embeddings.persisted_similarity_floor("all-MiniLM-L6-v2") == 0.25
        assert embeddings.persisted_similarity_floor("BAAI/bge-m3") == 0.60

    def test_migration_status_complete_only_when_fully_converted(
        self, tmp_db: sqlite3.Connection
    ) -> None:
        target = "BAAI/bge-m3"
        for sid, model in ((1, target), (2, "all-MiniLM-L6-v2")):
            tmp_db.execute(
                "INSERT INTO embeddings (source_table, source_id, text_hash, "
                "embedding, model_name) VALUES ('observations', ?, ?, ?, ?)",
                (sid, f"h{sid}", b"\x00\x00\x00\x00", model),
            )
        tmp_db.commit()
        st = embeddings.migration_status(tmp_db, target)
        assert st["complete"] is False and st["remaining"] == 1
        # convert the laggard
        tmp_db.execute(
            "UPDATE embeddings SET model_name = ? WHERE source_id = 2", (target,)
        )
        tmp_db.commit()
        st2 = embeddings.migration_status(tmp_db, target)
        assert st2["complete"] is True and st2["remaining"] == 0


class TestEmbeddingOutbox:
    """Wave 4: durable backfill of hot-path-skipped embeddings."""

    @REQUIRES_RAG
    def test_enqueue_idempotent_and_drain_embeds(self, tmp_db: sqlite3.Connection) -> None:
        tmp_db.execute(
            "INSERT INTO observations (id, session_id, title, narrative) "
            "VALUES (1, 's', 'Auth bug', 'jwt refresh fails')"
        )
        tmp_db.commit()
        assert embeddings.enqueue_outbox(tmp_db, "observations", 1) is True
        embeddings.enqueue_outbox(tmp_db, "observations", 1)  # idempotent
        assert tmp_db.execute("SELECT COUNT(*) FROM embedding_outbox").fetchone()[0] == 1

        rep = embeddings.drain_outbox(tmp_db)
        assert rep["drained"] == 1 and rep["remaining"] == 0
        assert (
            tmp_db.execute(
                "SELECT COUNT(*) FROM embeddings "
                "WHERE source_table='observations' AND source_id=1"
            ).fetchone()[0]
            == 1
        )
        assert tmp_db.execute("SELECT COUNT(*) FROM embedding_outbox").fetchone()[0] == 0

    @REQUIRES_RAG
    def test_drain_drops_gone_source(self, tmp_db: sqlite3.Connection) -> None:
        # A row whose source observation no longer exists is dropped, not
        # retried forever.
        tmp_db.execute(
            "INSERT INTO embedding_outbox (source_table, source_id, enqueued_at) "
            "VALUES ('observations', 999, 0)"
        )
        tmp_db.commit()
        embeddings.drain_outbox(tmp_db)
        assert tmp_db.execute("SELECT COUNT(*) FROM embedding_outbox").fetchone()[0] == 0

    def test_drain_unavailable_is_safe(self, tmp_db: sqlite3.Connection) -> None:
        with patch.object(embeddings, "is_available", return_value=False):
            rep = embeddings.drain_outbox(tmp_db)
            assert rep["status"] == "unavailable"


class TestTextHash:
    def test_hash_length_16(self) -> None:
        h = embeddings._compute_text_hash("any text")
        assert len(h) == 16

    def test_hash_deterministic(self) -> None:
        assert embeddings._compute_text_hash("same") == embeddings._compute_text_hash("same")

    def test_hash_different_inputs_differ(self) -> None:
        assert embeddings._compute_text_hash("a") != embeddings._compute_text_hash("b")
