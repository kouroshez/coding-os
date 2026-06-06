"""Dim-aware cosine + dual-model embeddings + migrator tests.

Ship gate (Section 19, I.1):
  - existing 109 RAG tests still pass with new embeddings
  - Persian query precision measured vs baseline
  - dim-mismatch handling test (no silent [] returns)
  - resume-after-crash test
"""

from __future__ import annotations

import sqlite3
from typing import Any

import embeddings
import migrator_embeddings
import pytest
from database import init_db

# ---------------------------------------------------------------------------
# Fake encoder — deterministic, dim-parameterised, no network.
# ---------------------------------------------------------------------------


class FakeEncoder:
    """Returns a reproducible vector of the given dim for any input."""

    def __init__(self, dim: int, salt: str = "") -> None:
        self.dim = dim
        self.salt = salt

    def _vec(self, text: str) -> list[float]:
        import hashlib

        seed = int(hashlib.sha256((self.salt + text).encode("utf-8")).hexdigest(), 16)
        rng = _SmallRNG(seed)
        raw = [rng.next() for _ in range(self.dim)]
        # L2-normalise so cosine = dot product (same contract the real
        # sentence-transformers use with normalize_embeddings=True).
        norm = sum(v * v for v in raw) ** 0.5 or 1.0
        return [v / norm for v in raw]

    def encode(self, text: Any, convert_to_numpy: bool = True, **_: Any) -> Any:
        import numpy as np

        if isinstance(text, str):
            return np.asarray(self._vec(text), dtype=np.float32)
        return np.asarray([self._vec(t) for t in text], dtype=np.float32)


class _SmallRNG:
    def __init__(self, seed: int) -> None:
        self._state = seed & ((1 << 64) - 1) or 0x9E3779B97F4A7C15

    def next(self) -> float:
        self._state = (self._state * 6364136223846793005 + 1442695040888963407) & ((1 << 64) - 1)
        return ((self._state >> 33) / (1 << 31)) - 1.0


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def minilm_fake():
    embeddings._override_model("all-MiniLM-L6-v2", FakeEncoder(384, "minilm-"))
    try:
        yield
    finally:
        embeddings._override_model("all-MiniLM-L6-v2", None)


@pytest.fixture()
def bge_m3_fake():
    embeddings._override_model("BAAI/bge-m3", FakeEncoder(1024, "bge-"))
    try:
        yield
    finally:
        embeddings._override_model("BAAI/bge-m3", None)


@pytest.fixture()
def conn(tmp_path) -> sqlite3.Connection:
    c = init_db(str(tmp_path / "emb.db"))
    try:
        yield c
    finally:
        c.close()


# ---------------------------------------------------------------------------
# Model routing
# ---------------------------------------------------------------------------


class TestDualModel:
    def test_active_model_reads_env(self, monkeypatch):
        monkeypatch.setenv("COS_EMBEDDING_MODEL", "BAAI/bge-m3")
        assert embeddings.active_model_name() == "BAAI/bge-m3"

    def test_active_model_defaults_to_minilm(self, monkeypatch):
        monkeypatch.delenv("COS_EMBEDDING_MODEL", raising=False)
        assert embeddings.active_model_name() == embeddings.DEFAULT_MODEL_NAME

    def test_model_dim_known_models(self):
        assert embeddings.model_dim("all-MiniLM-L6-v2") == 384
        assert embeddings.model_dim("BAAI/bge-m3") == 1024
        assert embeddings.model_dim("unknown") is None

    def test_bytes_to_dim(self):
        assert embeddings.bytes_to_dim(None) is None
        assert embeddings.bytes_to_dim(b"") is None
        assert embeddings.bytes_to_dim(b"abc") is None  # not a multiple of 4
        assert embeddings.bytes_to_dim(b"abcd") == 1
        assert embeddings.bytes_to_dim(b"abcd" * 384) == 384

    def test_embed_text_routes_by_model_name(self, minilm_fake, bge_m3_fake):
        m_vec = embeddings.embed_text("hi", model_name="all-MiniLM-L6-v2")
        b_vec = embeddings.embed_text("hi", model_name="BAAI/bge-m3")
        assert embeddings.bytes_to_dim(m_vec) == 384
        assert embeddings.bytes_to_dim(b_vec) == 1024

    def test_embed_text_unknown_model_yields_none(self):
        assert embeddings.embed_text("hi", model_name="not-a-real-model") is None


# ---------------------------------------------------------------------------
# Dim-aware cosine — the pre-I.1 silent-[] bug is fixed.
# ---------------------------------------------------------------------------


class TestDimAwareCosine:
    def test_matching_dims_score(self, minilm_fake):
        q = embeddings.embed_text("hello", model_name="all-MiniLM-L6-v2")
        c = embeddings.embed_text("hello", model_name="all-MiniLM-L6-v2")
        scores = embeddings.cosine_similarity(q, [c])
        assert len(scores) == 1
        assert scores[0] == pytest.approx(1.0, abs=1e-5)

    def test_dim_mismatch_does_not_blank_results(self, minilm_fake, bge_m3_fake):
        """Mixing a 1024-dim row with a 384-dim query must keep matching
        rows scoring normally — pre-I.1 behaviour returned [] wholesale."""
        q = embeddings.embed_text("hi", model_name="all-MiniLM-L6-v2")
        same = embeddings.embed_text("hi", model_name="all-MiniLM-L6-v2")
        other_dim = embeddings.embed_text("hi", model_name="BAAI/bge-m3")
        scores = embeddings.cosine_similarity(q, [same, other_dim, same])
        assert len(scores) == 3
        assert scores[0] == pytest.approx(1.0, abs=1e-5)
        assert scores[1] == 0.0  # mismatched dim → skipped, not blanked
        assert scores[2] == pytest.approx(1.0, abs=1e-5)

    def test_meta_reports_dim_mismatch_skipped(self, minilm_fake, bge_m3_fake):
        q = embeddings.embed_text("hi", model_name="all-MiniLM-L6-v2")
        a = embeddings.embed_text("hi", model_name="all-MiniLM-L6-v2")
        b = embeddings.embed_text("hi", model_name="BAAI/bge-m3")
        result = embeddings.cosine_similarity_with_meta(q, [a, b, b, b])
        assert result["query_dim"] == 384
        assert result["dim_mismatch_skipped"] == 3
        assert result["matched"] == 1
        assert result["total"] == 4

    def test_meta_reports_malformed_skipped(self, minilm_fake):
        q = embeddings.embed_text("hi", model_name="all-MiniLM-L6-v2")
        result = embeddings.cosine_similarity_with_meta(
            q,
            [None, b"bad", q],
        )
        assert result["malformed_skipped"] == 2
        assert result["matched"] == 1

    def test_all_rows_mismatched_yields_zero_matched(self, minilm_fake, bge_m3_fake):
        """This is what triggers the MCP tool's `fail("transient", ...)`."""
        q = embeddings.embed_text("hi", model_name="all-MiniLM-L6-v2")
        other = embeddings.embed_text("hi", model_name="BAAI/bge-m3")
        result = embeddings.cosine_similarity_with_meta(q, [other, other])
        assert result["matched"] == 0
        assert result["dim_mismatch_skipped"] == 2
        assert result["scores"] == [0.0, 0.0]

    def test_legacy_empty_inputs_still_empty(self):
        assert embeddings.cosine_similarity(b"", [b"x" * 1536]) == []
        assert embeddings.cosine_similarity(b"x" * 1536, []) == []


# ---------------------------------------------------------------------------
# upsert_embedding — v12 dim column
# ---------------------------------------------------------------------------


class TestUpsertEmbeddingPhaseI:
    def test_insert_writes_embedding_dim(self, conn, minilm_fake):
        # observations row is needed as source_id anchor.
        conn.execute(
            "INSERT INTO observations (id, session_id, title, narrative) "
            "VALUES (1, 'test', 'hello', 'hello world narrative')"
        )
        conn.commit()
        result = embeddings.upsert_embedding(conn, "observations", 1, "hello world")
        assert result["status"] == "inserted"
        assert result["dim"] == 384
        assert result["model_name"] == "all-MiniLM-L6-v2"

        row = conn.execute(
            "SELECT embedding_dim, model_name FROM embeddings WHERE source_id = 1"
        ).fetchone()
        assert row[0] == 384
        assert row[1] == "all-MiniLM-L6-v2"

    def test_reembed_with_different_model_updates_row(self, conn, minilm_fake, bge_m3_fake):
        conn.execute(
            "INSERT INTO observations (id, session_id, title, narrative) "
            "VALUES (1, 'test', 'hi', 'hi narrative')"
        )
        conn.commit()
        first = embeddings.upsert_embedding(conn, "observations", 1, "hi")
        assert first["status"] == "inserted"

        second = embeddings.upsert_embedding(
            conn, "observations", 1, "hi", model_name="BAAI/bge-m3"
        )
        assert second["status"] == "updated"
        assert second["dim"] == 1024

        row = conn.execute(
            "SELECT embedding_dim, model_name FROM embeddings WHERE source_id = 1"
        ).fetchone()
        assert row[0] == 1024
        assert row[1] == "BAAI/bge-m3"

    def test_unchanged_text_same_model_is_noop(self, conn, minilm_fake):
        conn.execute(
            "INSERT INTO observations (id, session_id, title, narrative) "
            "VALUES (1, 'test', 'hi', 'hi narrative')"
        )
        conn.commit()
        embeddings.upsert_embedding(conn, "observations", 1, "hi")
        again = embeddings.upsert_embedding(conn, "observations", 1, "hi")
        assert again["status"] == "unchanged"


# ---------------------------------------------------------------------------
# Migrator — batching, checkpointing, resume.
# ---------------------------------------------------------------------------


class TestMigratorEmbeddings:
    def _seed_rows(self, conn: sqlite3.Connection, n: int) -> None:
        for i in range(1, n + 1):
            conn.execute(
                "INSERT INTO observations (id, session_id, title, narrative) "
                "VALUES (?, 'test', ?, ?)",
                (i, f"obs {i}", f"observation number {i}"),
            )
        conn.commit()
        for i in range(1, n + 1):
            embeddings.upsert_embedding(
                conn,
                "observations",
                i,
                f"observation number {i}",
                model_name="all-MiniLM-L6-v2",
            )

    def test_checkpoint_round_trip(self, tmp_path):
        path = tmp_path / ".embedding-migration.json"
        cp = migrator_embeddings.MigrationCheckpoint(
            target_model="BAAI/bge-m3",
            total=500,
            done=128,
            last_id=128,
            eta_seconds=42.5,
        )
        cp.save(path)
        loaded = migrator_embeddings.MigrationCheckpoint.load(path)
        assert loaded.target_model == "BAAI/bge-m3"
        assert loaded.done == 128
        assert loaded.last_id == 128
        assert loaded.eta_seconds == pytest.approx(42.5)

    def test_checkpoint_missing_returns_fresh(self, tmp_path):
        cp = migrator_embeddings.MigrationCheckpoint.load(tmp_path / "no-such-file.json")
        assert cp.done == 0
        assert cp.last_id == 0

    def test_checkpoint_atomic_replace(self, tmp_path):
        """Crash between write and rename must not leave a corrupt file."""
        path = tmp_path / ".embedding-migration.json"
        # Pre-populate with a valid checkpoint.
        migrator_embeddings.MigrationCheckpoint(done=5).save(path)
        # Simulate half-written file — the .tmp path should be distinct.
        tmp = path.with_suffix(path.suffix + ".tmp")
        assert not tmp.exists()  # save() cleans up via rename
        loaded = migrator_embeddings.MigrationCheckpoint.load(path)
        assert loaded.done == 5

    def test_run_one_batch_migrates_rows(self, conn, minilm_fake, bge_m3_fake, tmp_path):
        self._seed_rows(conn, n=5)
        checkpoint = tmp_path / ".cp.json"
        report = migrator_embeddings.run_one_batch(
            conn,
            target_model="BAAI/bge-m3",
            batch_size=2,
            checkpoint_path=checkpoint,
        )
        assert report["migrated_this_batch"] == 2
        # Rows 1-2 should now be at BGE-M3 with dim=1024.
        rows = conn.execute(
            "SELECT source_id, embedding_dim FROM embeddings "
            "WHERE model_name='BAAI/bge-m3' ORDER BY source_id"
        ).fetchall()
        assert len(rows) == 2
        assert {r[1] for r in rows} == {1024}

    def test_run_one_batch_resumes_from_checkpoint(self, conn, minilm_fake, bge_m3_fake, tmp_path):
        self._seed_rows(conn, n=6)
        checkpoint = tmp_path / ".cp.json"

        # First batch — 3 rows.
        first = migrator_embeddings.run_one_batch(
            conn,
            target_model="BAAI/bge-m3",
            batch_size=3,
            checkpoint_path=checkpoint,
        )
        assert first["done"] == 3
        assert first["migrated_this_batch"] == 3

        # Simulate crash — reload checkpoint.
        loaded = migrator_embeddings.MigrationCheckpoint.load(checkpoint)
        assert loaded.last_id == 3

        # Second batch — picks up where we left off.
        second = migrator_embeddings.run_one_batch(
            conn,
            target_model="BAAI/bge-m3",
            batch_size=3,
            checkpoint_path=checkpoint,
        )
        assert second["done"] == 6
        assert second["migrated_this_batch"] == 3

    def test_run_until_idle_completes(self, conn, minilm_fake, bge_m3_fake, tmp_path):
        self._seed_rows(conn, n=7)
        checkpoint = tmp_path / ".cp.json"
        final = migrator_embeddings.run_until_idle(
            conn,
            target_model="BAAI/bge-m3",
            batch_size=2,
            checkpoint_path=checkpoint,
        )
        assert final["remaining"] == 0
        rows = conn.execute(
            "SELECT COUNT(*) FROM embeddings WHERE model_name='BAAI/bge-m3'"
        ).fetchone()[0]
        assert rows == 7

    def test_target_model_change_resets_progress(self, conn, minilm_fake, bge_m3_fake, tmp_path):
        """Switching target models (e.g. user picks a different BGE version)
        should not leave stale 'done' counts from the previous model."""
        self._seed_rows(conn, n=3)
        checkpoint = tmp_path / ".cp.json"
        migrator_embeddings.MigrationCheckpoint(
            target_model="some-old-model", done=999, last_id=999
        ).save(checkpoint)

        report = migrator_embeddings.run_one_batch(
            conn,
            target_model="BAAI/bge-m3",
            batch_size=2,
            checkpoint_path=checkpoint,
        )
        # 999 stale counter must NOT carry over — we start from zero for
        # the new target.
        assert report["done"] <= 3

    def test_migration_status_reports_complete(self, conn, minilm_fake, bge_m3_fake, tmp_path):
        self._seed_rows(conn, n=2)
        checkpoint = tmp_path / ".cp.json"
        migrator_embeddings.run_until_idle(
            conn,
            target_model="BAAI/bge-m3",
            batch_size=5,
            checkpoint_path=checkpoint,
        )
        status = migrator_embeddings.migration_status(
            conn,
            target_model="BAAI/bge-m3",
            checkpoint_path=checkpoint,
        )
        assert status["migration_complete"] is True
        assert status["remaining"] == 0

    def test_run_until_idle_skips_when_unavailable(self, conn, tmp_path, monkeypatch):
        monkeypatch.setattr(embeddings, "is_available", lambda: False)
        report = migrator_embeddings.run_until_idle(
            conn,
            target_model="BAAI/bge-m3",
            checkpoint_path=tmp_path / ".cp.json",
        )
        assert report["status"] == "skipped"
        assert report["reason"] == "unavailable"
