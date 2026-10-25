"""Embedding model SSOT, calibrated floors, and the re-embed cutover gate."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

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
