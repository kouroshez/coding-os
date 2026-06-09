"""graph_os — sqlite-vec ANN index over graph_node embeddings.

The ``embeddings`` BLOB table stays the source of truth; this builds a derived
``vec0`` virtual table for sublinear kNN so semantic search stays fast as the
graph grows by orders of magnitude. Every entry point degrades cleanly: if the
sqlite-vec extension is unavailable, callers fall back to the brute-force scan
(always correct, just O(N)).

DEPENDS: sqlite-vec (optional), the embeddings table (source_table='graph_nodes').
"""

from __future__ import annotations

import logging

logger = logging.getLogger("graph_os.vec_index")

_VEC_TABLE = "graph_vec"


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


def _index_dim(conn) -> int | None:
    row = conn.execute(
        "SELECT LENGTH(embedding) FROM embeddings "
        "WHERE source_table='graph_nodes' AND embedding IS NOT NULL LIMIT 1"
    ).fetchone()
    if not row or not row[0] or row[0] % 4:
        return None
    return row[0] // 4


def _table_exists(conn) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (_VEC_TABLE,)
        ).fetchone()
        is not None
    )


def rebuild(conn) -> dict:
    """(Re)build the vec0 ANN index from graph_node embeddings of the dominant dim.

    Rows whose dim differs from the index (mixed-model mid-migration) are left
    out — the brute-force path with its dual-model bridge covers them. Idempotent.
    """
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
    return {"status": "ok", "rows": n, "dim": dim}


def knn(conn, query_blob: bytes, k: int) -> list[tuple[int, float]] | None:
    """ANN kNN over graph_node vectors → [(graph_nodes.id, cosine_similarity)].

    Returns None when the extension is unavailable or the query errors, so the
    caller falls back to brute force. Builds the index lazily on first use.
    Vectors are unit-normalised, so vec0's L2 distance d maps to cosine by
    ``cos = 1 - d²/2`` — kNN order is identical to cosine order.
    """
    if not query_blob or not ensure_loaded(conn):
        return None
    try:
        if not _table_exists(conn):
            if rebuild(conn).get("status") != "ok":
                return None
        rows = conn.execute(
            f"SELECT rowid, distance FROM {_VEC_TABLE} "
            "WHERE embedding MATCH ? ORDER BY distance LIMIT ?",
            (query_blob, max(1, int(k))),
        ).fetchall()
    except Exception as exc:
        logger.debug("vec knn failed (%s); caller falls back to brute force", exc)
        return None
    return [(int(r[0]), 1.0 - (float(r[1]) ** 2) / 2.0) for r in rows]


__all__ = ["is_vec_available", "ensure_loaded", "rebuild", "knn"]
