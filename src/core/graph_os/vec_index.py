"""graph_os — ANN index over graph_node embeddings, with a fallback chain.

Backends, in preference order:
  1. usearch HNSW   — true sublinear O(log N) kNN; the scale answer (Wave 5).
  2. sqlite-vec vec0 — SIMD-accelerated *exact* (flat) scan; ~5x faster than
     numpy but still O(N) — a constant-factor win, not algorithmic (measured).
  3. brute force    — the caller's streaming numpy scan (knn returns None).

The ``embeddings`` BLOB table stays the source of truth; every index here is a
derived cache, rebuilt from it. Each layer degrades cleanly to the next, so the
``knn()`` contract holds regardless of what is installed.

DEPENDS: usearch (optional), sqlite-vec (optional), the embeddings table.
"""

from __future__ import annotations

import contextlib
import logging
from pathlib import Path

logger = logging.getLogger("graph_os.vec_index")

_VEC_TABLE = "graph_vec"
# Loaded usearch indexes, keyed by db-file path (or conn id for :memory:).
# Value: (index, indexed_row_count) — count drives cheap staleness detection.
_HNSW_CACHE: dict = {}


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _index_dim(conn) -> int | None:
    row = conn.execute(
        "SELECT LENGTH(embedding) FROM embeddings "
        "WHERE source_table='graph_nodes' AND embedding IS NOT NULL LIMIT 1"
    ).fetchone()
    if not row or not row[0] or row[0] % 4:
        return None
    return row[0] // 4


def _graph_node_count(conn) -> int:
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM embeddings WHERE source_table='graph_nodes'"
        ).fetchone()[0]
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Backend 1 — usearch HNSW (sublinear)
# ---------------------------------------------------------------------------


def has_usearch() -> bool:
    """True iff usearch + numpy are importable (the sublinear HNSW backend)."""
    try:
        import numpy  # noqa: F401
        import usearch.index  # noqa: F401

        return True
    except ImportError:
        return False


def _db_file(conn) -> str:
    try:
        for _seq, name, file in conn.execute("PRAGMA database_list").fetchall():
            if name == "main":
                return file or ""
    except Exception as exc:
        logger.debug("db_file probe failed: %s", exc)
    return ""


def _hnsw_path(conn) -> str | None:
    dbf = _db_file(conn)
    if not dbf:
        return None  # :memory: — no on-disk index, rebuild per process
    return str(Path(dbf).with_name(".graph-hnsw.usearch"))


def _hnsw_build(conn) -> dict:
    import numpy as np
    from usearch.index import Index

    dim = _index_dim(conn)
    if dim is None:
        return {"status": "empty", "rows": 0}
    idx = Index(ndim=dim, metric="cos", dtype="f32")
    cur = conn.execute(
        "SELECT source_id, embedding FROM embeddings WHERE source_table='graph_nodes'"
    )
    n = 0
    while True:
        batch = cur.fetchmany(4096)
        if not batch:
            break
        keys, vecs = [], []
        for sid, blob in batch:
            if blob and len(blob) // 4 == dim:
                keys.append(int(sid))
                vecs.append(np.frombuffer(blob, dtype=np.float32))
        if keys:
            idx.add(np.array(keys, dtype=np.int64), np.vstack(vecs))
            n += len(keys)
    path = _hnsw_path(conn)
    if path:
        with contextlib.suppress(Exception):
            idx.save(path)
    _HNSW_CACHE[path or id(conn)] = (idx, n)
    return {"status": "ok", "rows": n, "dim": dim, "backend": "usearch-hnsw"}


def _hnsw_load(conn):
    from usearch.index import Index

    key = _hnsw_path(conn) or id(conn)
    count = _graph_node_count(conn)
    cached = _HNSW_CACHE.get(key)
    if cached and cached[1] == count:
        return cached[0]
    path = _hnsw_path(conn)
    if path and Path(path).exists():
        try:
            idx = Index.restore(path)
            if idx is not None and len(idx) == count:
                _HNSW_CACHE[key] = (idx, count)
                return idx
        except Exception as exc:
            logger.debug("hnsw restore failed (%s); rebuilding", exc)
    if _hnsw_build(conn).get("status") != "ok":
        return None
    entry = _HNSW_CACHE.get(key)
    return entry[0] if entry else None


def _hnsw_knn(conn, query_blob: bytes, k: int) -> list[tuple[int, float]] | None:
    import numpy as np

    try:
        idx = _hnsw_load(conn)
        if idx is None or len(idx) == 0:
            return None
        q = np.frombuffer(query_blob, dtype=np.float32)
        res = idx.search(q, max(1, int(k)))
        # usearch 'cos' returns cosine DISTANCE in [0,2]; similarity = 1 - dist.
        return [
            (int(key), 1.0 - float(dist))
            for key, dist in zip(res.keys, res.distances, strict=False)
        ]
    except Exception as exc:
        logger.debug("hnsw knn failed (%s); falling back", exc)
        return None


# ---------------------------------------------------------------------------
# Backend 2 — sqlite-vec vec0 (flat SIMD exact)
# ---------------------------------------------------------------------------


def is_vec_available() -> bool:
    """True iff sqlite-vec is importable and this python's sqlite3 can load it."""
    try:
        import sqlite3

        import sqlite_vec  # noqa: F401

        return hasattr(sqlite3.Connection, "enable_load_extension")
    except ImportError:
        return False


def ensure_loaded(conn) -> bool:
    """Load the sqlite-vec extension into conn. Returns True on success."""
    if not is_vec_available():
        return False
    try:
        import sqlite_vec

        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        return True
    except Exception as exc:
        logger.debug("sqlite-vec load failed: %s", exc)
        return False


def _vec0_exists(conn) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (_VEC_TABLE,)
        ).fetchone()
        is not None
    )


def _vec0_build(conn) -> dict:
    if not ensure_loaded(conn):
        return {"status": "unavailable", "rows": 0}
    dim = _index_dim(conn)
    if dim is None:
        return {"status": "empty", "rows": 0}
    conn.execute(f"DROP TABLE IF EXISTS {_VEC_TABLE}")
    conn.execute(f"CREATE VIRTUAL TABLE {_VEC_TABLE} USING vec0(embedding float[{dim}])")
    n = 0
    cur = conn.execute(
        "SELECT source_id, embedding FROM embeddings WHERE source_table='graph_nodes'"
    )
    while True:
        batch = cur.fetchmany(2000)
        if not batch:
            break
        for sid, blob in batch:
            if blob and len(blob) // 4 == dim:
                conn.execute(
                    f"INSERT INTO {_VEC_TABLE}(rowid, embedding) VALUES (?, ?)", (sid, blob)
                )
                n += 1
    conn.commit()
    return {"status": "ok", "rows": n, "dim": dim, "backend": "sqlite-vec"}


def _vec0_knn(conn, query_blob: bytes, k: int) -> list[tuple[int, float]] | None:
    if not ensure_loaded(conn):
        return None
    try:
        if not _vec0_exists(conn) and _vec0_build(conn).get("status") != "ok":
            return None
        rows = conn.execute(
            f"SELECT rowid, distance FROM {_VEC_TABLE} "
            "WHERE embedding MATCH ? ORDER BY distance LIMIT ?",
            (query_blob, max(1, int(k))),
        ).fetchall()
    except Exception as exc:
        logger.debug("vec0 knn failed (%s); caller falls back to brute force", exc)
        return None
    # Unit-normalised vectors: vec0 L2 distance d → cosine = 1 - d²/2.
    return [(int(r[0]), 1.0 - (float(r[1]) ** 2) / 2.0) for r in rows]


# ---------------------------------------------------------------------------
# Public API — dispatch across the fallback chain
# ---------------------------------------------------------------------------


def rebuild(conn) -> dict:
    """(Re)build the best available ANN index from graph_node embeddings."""
    if has_usearch():
        return _hnsw_build(conn)
    return _vec0_build(conn)


def knn(conn, query_blob: bytes, k: int) -> list[tuple[int, float]] | None:
    """kNN over graph_node vectors → [(graph_nodes.id, cosine_similarity)].

    Tries usearch HNSW (sublinear) → sqlite-vec flat → None (caller brute-forces).
    Builds the chosen index lazily on first use.
    """
    if not query_blob:
        return None
    if has_usearch():
        out = _hnsw_knn(conn, query_blob, k)
        if out is not None:
            return out
    return _vec0_knn(conn, query_blob, k)


__all__ = [
    "ensure_loaded",
    "has_usearch",
    "is_vec_available",
    "knn",
    "rebuild",
]
