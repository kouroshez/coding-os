"""
Coding OS — Vector embeddings module for RAG retrieval.

Provides semantic search via sentence-transformers + numpy cosine similarity
backed by a single SQLite `embeddings` table. Designed for graceful degradation:
if `sentence-transformers` or `numpy` is not installed, every public function
returns a safe falsy value and callers fall back to FTS5/LIKE.

Storage:
    embeddings table (created by db.py migration v5):
      id, source_table, source_id, text_hash, embedding (BLOB), model_name, created_at
      UNIQUE(source_table, source_id)

Vector format:
    numpy float32 array, 384 dimensions for `all-MiniLM-L6-v2`.
    Stored as raw bytes (1536 bytes per vector).

Public API:
    is_available()           -> bool
    embed_text(text)         -> bytes | None
    embed_texts(texts)       -> list[bytes | None]
    cosine_similarity(query, candidates) -> list[float]
    upsert_embedding(conn, source_table, source_id, text) -> dict
    search_similar(conn, query, source_tables, limit, threshold) -> list[dict]
    has_embeddings_data(conn) -> bool
    reindex_all(conn)        -> dict

CLI entry point:
    python -m embeddings --reindex
"""

from __future__ import annotations

import heapq
import sqlite3
import sys
from typing import Any

# Streaming batch sizes — bound peak memory regardless of table size.
# search streams candidate vectors; reindex streams + batch-embeds source rows.
_SEARCH_BATCH = 4096
_REINDEX_BATCH = 64

# The three private siblings this module was split into. Names are re-exported
# so `embeddings.<name>` keeps resolving for every caller and every test patch.
# Loaded flat as `embeddings` by thinking_os and as `thinking_os.embeddings`
# by graph_os; the relative form has no parent package under the first.
try:
    from ._embeddings_model import (
        _MODEL_OVERRIDES,
        _get_model,
        _get_model_by_name,
        _override_model,
        embed_text,
        embed_texts,
        is_available,
    )
    from ._embeddings_registry import (
        _DOC_FLOORS,
        _MEMORY_FLOORS,
        _PERSISTED_FLOORS,
        DEFAULT_MODEL_NAME,
        DEFAULT_SOURCE_TABLES,
        EMBEDDING_BYTES,
        EMBEDDING_DIM,
        GRAPH_EMBED_KINDS,
        MODEL_DIMS,
        _active_model_marker_path,
        active_model_name,
        bytes_to_dim,
        doc_similarity_floor,
        logger,
        memory_similarity_floor,
        migration_status,
        model_dim,
        persisted_similarity_floor,
        set_active_model,
    )
    from ._embeddings_store import (
        _compute_text_hash,
        _has_embedding_dim_column,
        _persist_embedding,
        has_embeddings_data,
        upsert_embedding,
    )
except ImportError:  # pragma: no cover
    from _embeddings_model import (  # type: ignore[no-redef]  # noqa: F401
        _MODEL_OVERRIDES,
        _get_model,
        _get_model_by_name,
        _override_model,
        embed_text,
        embed_texts,
        is_available,
    )
    from _embeddings_registry import (  # type: ignore[no-redef]  # noqa: F401
        _DOC_FLOORS,
        _MEMORY_FLOORS,
        _PERSISTED_FLOORS,
        DEFAULT_MODEL_NAME,
        DEFAULT_SOURCE_TABLES,
        EMBEDDING_BYTES,
        EMBEDDING_DIM,
        GRAPH_EMBED_KINDS,
        MODEL_DIMS,
        _active_model_marker_path,
        active_model_name,
        bytes_to_dim,
        doc_similarity_floor,
        logger,
        memory_similarity_floor,
        migration_status,
        model_dim,
        persisted_similarity_floor,
        set_active_model,
    )
    from _embeddings_store import (  # type: ignore[no-redef]  # noqa: F401
        _compute_text_hash,
        _has_embedding_dim_column,
        _persist_embedding,
        has_embeddings_data,
        upsert_embedding,
    )

# ---------------------------------------------------------------------------
# Similarity computation (numpy cosine on normalized vectors → just dot product)
# ---------------------------------------------------------------------------


def cosine_similarity(query_vec: bytes, candidate_vecs: list[bytes]) -> list[float]:
    """Compute cosine similarity — dim-aware."""
    if not query_vec or not candidate_vecs:
        return []
    return cosine_similarity_with_meta(query_vec, candidate_vecs)["scores"]


def cosine_similarity_with_meta(
    query_vec: bytes,
    candidate_vecs: list[bytes],
) -> dict:
    """Dim-aware cosine with diagnostic metadata."""
    default = {
        "scores": [0.0] * len(candidate_vecs),
        "query_dim": bytes_to_dim(query_vec),
        "dim_mismatch_skipped": 0,
        "malformed_skipped": 0,
        "total": len(candidate_vecs),
        "matched": 0,
    }
    if not query_vec or not candidate_vecs:
        return default
    if not is_available():
        return default
    try:
        import numpy as np

        query_dim = bytes_to_dim(query_vec)
        if query_dim is None:
            default["malformed_skipped"] = 1
            return default
        query = np.frombuffer(query_vec, dtype=np.float32)

        scores = [0.0] * len(candidate_vecs)
        valid_rows: list[Any] = []
        valid_idx: list[int] = []
        dim_mismatch = 0
        malformed = 0

        for i, c in enumerate(candidate_vecs):
            if not c:
                malformed += 1
                continue
            c_dim = bytes_to_dim(c)
            if c_dim is None:
                malformed += 1
                continue
            if c_dim != query_dim:
                dim_mismatch += 1
                continue
            valid_rows.append(np.frombuffer(c, dtype=np.float32))
            valid_idx.append(i)

        if valid_rows:
            matrix = np.vstack(valid_rows)
            raw = matrix @ query
            for j, idx in enumerate(valid_idx):
                scores[idx] = float(raw[j])

        return {
            "scores": scores,
            "query_dim": query_dim,
            "dim_mismatch_skipped": dim_mismatch,
            "malformed_skipped": malformed,
            "total": len(candidate_vecs),
            "matched": len(valid_rows),
        }
    except Exception as exc:
        logger.warning("cosine_similarity_with_meta failed: %s", exc)
        return default


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


def search_similar(
    conn: sqlite3.Connection,
    query: str,
    source_tables: list[str] | None = None,
    limit: int = 5,
    threshold: float = 0.1,
) -> list[dict]:
    """Find rows whose embeddings are most similar to the query text.

    Args:
        conn: Open SQLite connection.
        query: Natural language query.
        source_tables: Optional filter — only return matches from these
                       source_table values. Defaults to None (all tables).
        limit: Max results (capped at 100).
        threshold: Minimum cosine similarity to return (default 0.1 — tuned
            for all-MiniLM-L6-v2 on short text where typical "related" scores
            land in the 0.1-0.3 range and "unrelated" stays below 0.1).

    Returns:
        List of dicts: [{source_table, source_id, score}], sorted desc by score.
        Empty list if embeddings unavailable, table missing, or query empty.
    """
    if not query or not query.strip():
        return []
    if not is_available():
        return []
    if not has_embeddings_data(conn):
        return []

    # Dual-model bridge (M4): a DB mid-migration holds vectors from >1 model
    # at different dims. Encode the query with EVERY model present in the
    # target population, then score each candidate against the matching-dim
    # query vector. Dim-aware cosine returns 0 for mismatched dims, so an
    # element-wise max over the per-model score vectors collapses to "the
    # score from the candidate's own model" — no row is ever silently
    # invisible regardless of migration progress.
    model_sql = "SELECT DISTINCT model_name FROM embeddings"
    model_params: list[Any] = []
    if source_tables:
        ph = ",".join("?" * len(source_tables))
        model_sql += f" WHERE source_table IN ({ph})"
        model_params.extend(source_tables)
    try:
        present_models = [r[0] for r in conn.execute(model_sql, model_params).fetchall() if r[0]]
    except sqlite3.OperationalError:
        present_models = []
    if not present_models:
        present_models = [active_model_name()]
    query_vecs = [v for v in (embed_text(query, model_name=m) for m in present_models) if v]
    if not query_vecs:
        return []

    # Cap limit to prevent runaway queries
    limit = max(1, min(int(limit), 100))

    sql = "SELECT source_table, source_id, embedding FROM embeddings"
    params: list[Any] = []
    if source_tables:
        placeholders = ",".join("?" * len(source_tables))
        sql += f" WHERE source_table IN ({placeholders})"
        params.extend(source_tables)

    try:
        cursor = conn.execute(sql, params)
    except sqlite3.OperationalError as exc:
        logger.warning("search_similar query failed: %s", exc)
        return []

    # Stream candidates in batches and keep only a top-`limit` min-heap, so peak
    # memory is one batch of vectors + `limit` results — never the whole table
    # (1M embeddings fetched at once would be ~1.5 GB of RAM).
    heap: list[tuple[float, int, dict]] = []
    seq = 0
    while True:
        batch = cursor.fetchmany(_SEARCH_BATCH)
        if not batch:
            break
        cand_vecs = [r[2] for r in batch]
        if len(query_vecs) == 1:
            scores = cosine_similarity(query_vecs[0], cand_vecs)
        else:
            per_model = [cosine_similarity(qv, cand_vecs) for qv in query_vecs]
            scores = [max(col) for col in zip(*per_model, strict=False)]
        for i, score in enumerate(scores):
            if score < threshold:
                continue
            entry = (
                score,
                seq,
                {"source_table": batch[i][0], "source_id": batch[i][1], "score": score},
            )
            if len(heap) < limit:
                heapq.heappush(heap, entry)
            elif score > heap[0][0]:
                heapq.heapreplace(heap, entry)
            seq += 1

    results = [item for _, _, item in heap]
    results.sort(key=lambda d: d["score"], reverse=True)
    return results


# ---------------------------------------------------------------------------
# Outbox — durable deferral of hot-path-skipped embeddings
# ---------------------------------------------------------------------------
# Re-exported so `embeddings.drain_outbox` keeps resolving for the Stop-hook
# helper and for tests that monkeypatch it on this module.


def enqueue_outbox(conn: sqlite3.Connection, source_table: str, source_id: int) -> bool:
    """Record that (source_table, source_id) needs an embedding, off the hot path."""
    from embedding_outbox import enqueue_outbox as _enqueue

    return _enqueue(conn, source_table, source_id)


def drain_outbox(conn: sqlite3.Connection, *, limit: int = 128, max_attempts: int = 3) -> dict:
    """Embed up to `limit` pending outbox rows; remove on success, retry-bounded."""
    from embedding_outbox import drain_outbox as _drain

    return _drain(conn, limit=limit, max_attempts=max_attempts)


# ---------------------------------------------------------------------------
# Reindex (bootstrap / model upgrade)
# ---------------------------------------------------------------------------


def reindex_all(conn: sqlite3.Connection) -> dict:
    """Re-embed every row in every supported source table.

    Walks observations, learned_patterns, outcome_history, document_chunks,
    and tasks (when present), and calls upsert_embedding for each. Skips
    rows that already have an unchanged embedding (text_hash match).

    Used by `make cos-reindex` after a model upgrade or to bootstrap an
    existing DB.

    Returns:
        {table_name: {processed, inserted, updated, unchanged, skipped}}.
    """
    if not is_available():
        return {"status": "skipped", "reason": "unavailable"}

    report: dict[str, dict[str, int]] = {}

    handlers = [
        (
            "observations",
            "SELECT id, title, narrative, concepts FROM observations",
            lambda r: " ".join(filter(None, [r["title"], r["narrative"], r["concepts"]])),
        ),
        (
            "learned_patterns",
            "SELECT id, pattern, concepts FROM learned_patterns",
            lambda r: " ".join(filter(None, [r["pattern"], r["concepts"]])),
        ),
        (
            "outcome_history",
            "SELECT id, narrative_key_insight, narrative_what_failed, narrative_what_worked FROM outcome_history",
            lambda r: " ".join(
                filter(
                    None,
                    [
                        r["narrative_key_insight"],
                        r["narrative_what_failed"],
                        r["narrative_what_worked"],
                    ],
                )
            ),
        ),
        (
            "document_chunks",
            "SELECT id, heading_path, content FROM document_chunks",
            lambda r: " ".join(filter(None, [r["heading_path"], r["content"]])),
        ),
        (
            "graph_nodes",
            "SELECT id, label, signature, doc_blob FROM graph_nodes WHERE kind IN ("
            + ",".join(f"'{k}'" for k in GRAPH_EMBED_KINDS)
            + ")",
            lambda r: " ".join(filter(None, [r["label"], r["signature"], r["doc_blob"]])),
        ),
    ]

    name = active_model_name()
    has_dim_col = _has_embedding_dim_column(conn)

    for table, query, text_builder in handlers:
        stats = {"processed": 0, "inserted": 0, "updated": 0, "unchanged": 0, "skipped": 0}
        try:
            cursor = conn.execute(query)
        except sqlite3.OperationalError:
            # Table doesn't exist yet (e.g. document_chunks before v5)
            report[table] = stats
            continue
        # Stream source rows in batches; embed only changed/new rows in one
        # embed_texts() call per batch instead of one model.encode per row.
        # Peak memory = one batch, not the whole table.
        while True:
            src_rows = cursor.fetchmany(_REINDEX_BATCH)
            if not src_rows:
                break
            pending: list[tuple[int, str, int | None]] = []  # (source_id, text_hash, existing_id)
            texts: list[str] = []
            for row in src_rows:
                stats["processed"] += 1
                text = text_builder(row)
                if not text or not text.strip():
                    stats["skipped"] += 1
                    continue
                text_hash = _compute_text_hash(text)
                existing = conn.execute(
                    "SELECT id, text_hash, model_name FROM embeddings "
                    "WHERE source_table = ? AND source_id = ?",
                    (table, row["id"]),
                ).fetchone()
                if existing and existing[1] == text_hash and existing[2] == name:
                    stats["unchanged"] += 1
                    continue
                pending.append((row["id"], text_hash, existing[0] if existing else None))
                texts.append(text)
            if not texts:
                continue
            vectors = embed_texts(texts, model_name=name)
            for (source_id, text_hash, existing_id), vector in zip(pending, vectors, strict=False):
                if vector is None:
                    stats["skipped"] += 1
                    continue
                try:
                    status, _, _ = _persist_embedding(
                        conn, table, source_id, text_hash, vector, name, existing_id, has_dim_col
                    )
                except sqlite3.OperationalError:
                    stats["skipped"] += 1
                    continue
                stats[status] += 1
            conn.commit()
        report[table] = stats

    return report


# ---------------------------------------------------------------------------
# CLI entry point — `python -m embeddings --reindex`
# ---------------------------------------------------------------------------


def _main() -> None:
    import argparse
    import json
    from pathlib import Path

    parser = argparse.ArgumentParser(description="Embeddings CLI for coding-os RAG")
    parser.add_argument(
        "--reindex", action="store_true", help="Re-embed all rows in supported tables"
    )
    parser.add_argument(
        "--db", type=str, default=None, help="Override DB path (defaults to COS_DB_PATH)"
    )
    args = parser.parse_args()

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from database import init_db

    if not is_available():
        print(
            "ERROR: sentence-transformers not installed. Run: uv sync --extra rag", file=sys.stderr
        )
        sys.exit(1)

    conn = init_db(args.db)
    if args.reindex:
        result = reindex_all(conn)
        print(json.dumps(result, indent=2))
    else:
        from database import get_db_stats

        stats = get_db_stats(conn)
        print(
            json.dumps({"status": "ok", "embeddings_available": True, "db_stats": stats}, indent=2)
        )
    conn.close()


if __name__ == "__main__":
    _main()
