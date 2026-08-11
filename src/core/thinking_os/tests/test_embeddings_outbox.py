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
        tmp_db.execute("UPDATE embeddings SET model_name = ? WHERE source_id = 2", (target,))
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
                "SELECT COUNT(*) FROM embeddings WHERE source_table='observations' AND source_id=1"
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


class TestDrainOutboxReconciliation:
    def test_already_embedded_row_reconciled_without_model(self, tmp_db) -> None:
        tmp_db.execute(
            "INSERT INTO embeddings (source_table, source_id, text_hash, embedding) "
            "VALUES ('observations', 42, 'h', ?)",
            (b"\x00\x00\x00",),
        )
        tmp_db.execute(
            "INSERT INTO embedding_outbox (source_table, source_id, enqueued_at) "
            "VALUES ('observations', 42, 0)"
        )
        tmp_db.commit()

        with patch("embeddings.is_available", return_value=False):
            result = embeddings.drain_outbox(tmp_db, limit=10)

        assert result["status"] == "unavailable"
        remaining = tmp_db.execute(
            "SELECT COUNT(*) FROM embedding_outbox WHERE source_table = 'observations' AND source_id = 42"
        ).fetchone()[0]
        assert remaining == 0

    def test_unembedded_row_survives_when_model_unavailable(self, tmp_db) -> None:
        tmp_db.execute(
            "INSERT INTO embedding_outbox (source_table, source_id, enqueued_at) "
            "VALUES ('observations', 99, 0)"
        )
        tmp_db.commit()

        with patch("embeddings.is_available", return_value=False):
            embeddings.drain_outbox(tmp_db, limit=10)

        remaining = tmp_db.execute(
            "SELECT COUNT(*) FROM embedding_outbox WHERE source_id = 99"
        ).fetchone()[0]
        assert remaining == 1
