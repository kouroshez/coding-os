"""Wave 3: sqlite-vec ANN index over graph_node embeddings."""

from __future__ import annotations

import pytest

from graph_os import vec_index


def _unit_blob(xs):
    import numpy as np

    v = np.array(xs, dtype=np.float32)
    return (v / np.linalg.norm(v)).astype(np.float32).tobytes()


def _seed(conn, vectors: dict[int, list[float]]) -> None:
    for nid, vec in vectors.items():
        conn.execute(
            "INSERT INTO graph_nodes (id, kind, label, uid, created_at, updated_at) "
            "VALUES (?, 'function', ?, ?, 0, 0)",
            (nid, f"n{nid}", f"code:function:t.py::n{nid}"),
        )
        conn.execute(
            "INSERT INTO embeddings (source_table, source_id, text_hash, embedding, "
            "model_name, embedding_dim) VALUES ('graph_nodes', ?, ?, ?, 'test', ?)",
            (nid, f"h{nid}", _unit_blob(vec), len(vec)),
        )
    conn.commit()


class TestVecIndex:
    def test_rebuild_and_knn_match_cosine_order(self, migrated_conn):
        if not (vec_index.has_usearch() or vec_index.is_vec_available()):
            pytest.skip("no ANN backend (usearch / sqlite-vec) available")
        _seed(
            migrated_conn,
            {
                1: [1, 0, 0, 0, 0, 0, 0, 0],  # exact match to query
                2: [0.9, 0.1, 0, 0, 0, 0, 0, 0],  # near
                3: [0, 0, 0, 0, 0, 0, 0, 1],  # far (orthogonal)
            },
        )
        rep = vec_index.rebuild(migrated_conn)
        assert rep["status"] == "ok" and rep["rows"] == 3 and rep["dim"] == 8

        out = vec_index.knn(migrated_conn, _unit_blob([1, 0, 0, 0, 0, 0, 0, 0]), k=3)
        assert out is not None
        ids = [gid for gid, _ in out]
        assert ids[0] == 1  # exact match ranks first
        assert ids[1] == 2  # near second
        # cosine descending
        sims = [cos for _, cos in out]
        assert sims == sorted(sims, reverse=True)
        assert sims[0] == pytest.approx(1.0, abs=1e-4)

    def test_knn_lazy_builds_when_missing(self, migrated_conn):
        if not (vec_index.has_usearch() or vec_index.is_vec_available()):
            pytest.skip("no ANN backend available")
        _seed(migrated_conn, {1: [1, 0, 0, 0]})
        # no explicit rebuild — knn must build the index on first use
        out = vec_index.knn(migrated_conn, _unit_blob([1, 0, 0, 0]), k=1)
        assert out is not None and out[0][0] == 1

    def test_knn_returns_none_when_no_backend(self, migrated_conn, monkeypatch):
        # Both ANN backends absent → None signals the caller to brute-force.
        monkeypatch.setattr(vec_index, "has_usearch", lambda: False)
        monkeypatch.setattr(vec_index, "is_vec_available", lambda: False)
        assert vec_index.knn(migrated_conn, b"\x00\x00\x00\x00", k=5) is None

    def test_rebuild_empty_pool_is_safe(self, migrated_conn):
        if not (vec_index.has_usearch() or vec_index.is_vec_available()):
            pytest.skip("no ANN backend available")
        rep = vec_index.rebuild(migrated_conn)
        assert rep["status"] == "empty" and rep["rows"] == 0

    def test_usearch_is_preferred_backend(self, migrated_conn):
        if not vec_index.has_usearch():
            pytest.skip("usearch not installed")
        _seed(migrated_conn, {1: [1, 0, 0, 0, 0, 0, 0, 0], 2: [0, 1, 0, 0, 0, 0, 0, 0]})
        rep = vec_index.rebuild(migrated_conn)
        assert rep.get("backend") == "usearch-hnsw" and rep["rows"] == 2
