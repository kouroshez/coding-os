"""
Coding OS — Vector embeddings module for RAG retrieval (Phase B).

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

import functools
import hashlib
import logging
import sqlite3
import sys
from typing import Any

logger = logging.getLogger("coding_os.embeddings")

# Default model — small, fast, MIT license. ~22MB download.
DEFAULT_MODEL_NAME = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384  # Dimensions of all-MiniLM-L6-v2 output (legacy default)
EMBEDDING_BYTES = EMBEDDING_DIM * 4  # float32 → 4 bytes per dimension

# I.1 — Phase I: dual-model support during the MiniLM → BGE-M3 migration.
# Each entry: output dim per model. Callers can opt into BGE-M3 via the
# COS_EMBEDDING_MODEL env var or an explicit model_name kwarg. The DB
# remembers the model_name + embedding_dim per row so mixed populations
# are queryable through dim-aware cosine_similarity.
MODEL_DIMS: dict[str, int] = {
    "all-MiniLM-L6-v2": 384,
    "BAAI/bge-m3": 1024,
}

# Source tables that support embedded retrieval. New tables can be added
# without code changes — just call upsert_embedding with the new table name.
DEFAULT_SOURCE_TABLES = (
    "observations",
    "learned_patterns",
    "outcome_history",
    "document_chunks",
    "tasks",
)


def active_model_name() -> str:
    """Return the model the *current* process should encode with."""
    import os

    return os.environ.get("COS_EMBEDDING_MODEL", DEFAULT_MODEL_NAME).strip() or DEFAULT_MODEL_NAME


def model_dim(model_name: str) -> int | None:
    """Return the expected vector dim for a known model, else None."""
    return MODEL_DIMS.get(model_name)


def bytes_to_dim(payload: bytes | None) -> int | None:
    """Return dim inferred from a raw float32 blob (len / 4)."""
    if not payload:
        return None
    if len(payload) % 4 != 0:
        return None
    return len(payload) // 4


# ---------------------------------------------------------------------------
# Availability detection — graceful degradation entry point
# ---------------------------------------------------------------------------

@functools.lru_cache(maxsize=1)
def is_available() -> bool:
    """Return True iff sentence-transformers and numpy are importable.

    Result is cached for the process lifetime — checking is cheap after the
    first call.

    Returns:
        True if both `sentence_transformers` and `numpy` import successfully.
        False otherwise — callers must handle this and fall back.
    """
    try:
        import numpy  # noqa: F401
        import sentence_transformers  # noqa: F401
        return True
    except ImportError:
        return False


@functools.lru_cache(maxsize=4)
def _get_model_by_name(name: str) -> Any:
    """Load and cache an embedding model by name."""
    if not is_available():
        return None
    override = _MODEL_OVERRIDES.get(name)
    if override is not None:
        return override
    try:
        from sentence_transformers import SentenceTransformer
        logger.info("Loading embedding model: %s", name)
        return SentenceTransformer(name)
    except Exception as exc:  # noqa: BLE001 — tolerate corrupt downloads
        logger.warning("Failed to load embedding model %s: %s", name, exc)
        return None


# Test hook: a mapping of model_name → pre-built encoder (duck-typed to
# expose .encode(...) with the sentence-transformers signature). Lets the
# test suite exercise dual-model behaviour without downloading BGE-M3.
_MODEL_OVERRIDES: dict[str, Any] = {}


def _override_model(name: str, encoder: Any) -> None:
    """Test-only: install a fake encoder for the given model name."""
    if encoder is None:
        _MODEL_OVERRIDES.pop(name, None)
    else:
        _MODEL_OVERRIDES[name] = encoder
    _get_model_by_name.cache_clear()
    _get_model.cache_clear()


@functools.lru_cache(maxsize=1)
def _get_model() -> Any:
    """Legacy shim — returns the active-model encoder.

    Kept as an lru_cache'd function so existing tests that call
    `_get_model.cache_clear()` continue to work after the Phase I
    refactor. Defers to the multi-model loader.
    """
    return _get_model_by_name(active_model_name())


# ---------------------------------------------------------------------------
# Embedding generation
# ---------------------------------------------------------------------------

def embed_text(text: str, model_name: str | None = None) -> bytes | None:
    """Embed a single text string with the active (or explicit) model."""
    if not text or not text.strip():
        return None
    # When the caller doesn't pick a model, route through the legacy
    # _get_model() so existing tests that patch it keep working.
    if model_name is None:
        model = _get_model()
        name = active_model_name()
    else:
        name = model_name
        model = _get_model_by_name(name)
    if model is None:
        return None
    try:
        import numpy as np
        vector = model.encode(text, convert_to_numpy=True, normalize_embeddings=True)
        return np.asarray(vector, dtype=np.float32).tobytes()
    except Exception as exc:  # noqa: BLE001
        logger.warning("embed_text(%s) failed: %s", name, exc)
        return None


def embed_texts(
    texts: list[str], model_name: str | None = None
) -> list[bytes | None]:
    """Batch-embed with the active (or explicit) model."""
    if not texts:
        return []
    if model_name is None:
        model = _get_model()
        name = active_model_name()
    else:
        name = model_name
        model = _get_model_by_name(name)
    if model is None:
        return [None] * len(texts)
    try:
        import numpy as np
        indices = [i for i, t in enumerate(texts) if t and t.strip()]
        valid_texts = [texts[i] for i in indices]
        if not valid_texts:
            return [None] * len(texts)
        vectors = model.encode(
            valid_texts,
            convert_to_numpy=True,
            normalize_embeddings=True,
            batch_size=32,
        )
        results: list[bytes | None] = [None] * len(texts)
        for idx, vec in zip(indices, vectors):
            results[idx] = np.asarray(vec, dtype=np.float32).tobytes()
        return results
    except Exception as exc:  # noqa: BLE001
        logger.warning("embed_texts(%s) failed: %s", name, exc)
        return [None] * len(texts)


# ---------------------------------------------------------------------------
# Similarity computation (numpy cosine on normalized vectors → just dot product)
# ---------------------------------------------------------------------------

def cosine_similarity(query_vec: bytes, candidate_vecs: list[bytes]) -> list[float]:
    """Compute cosine similarity — dim-aware (Phase I contract)."""
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
    except Exception as exc:  # noqa: BLE001
        logger.warning("cosine_similarity_with_meta failed: %s", exc)
        return default


# ---------------------------------------------------------------------------
# Text hashing — staleness detection
# ---------------------------------------------------------------------------

def _compute_text_hash(text: str) -> str:
    """Return the first 16 hex chars of SHA256(text).

    Matches the pattern used by capture._compute_content_hash so the codebase
    has one consistent hashing convention.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def has_embeddings_data(conn: sqlite3.Connection) -> bool:
    """Return True if the embeddings table exists and contains at least one row."""
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='embeddings'"
        ).fetchone()
        if row is None:
            return False
        count = conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()
        return bool(count and count[0] > 0)
    except sqlite3.OperationalError:
        return False


def upsert_embedding(
    conn: sqlite3.Connection,
    source_table: str,
    source_id: int,
    text: str,
    *,
    model_name: str | None = None,
) -> dict:
    """Insert or refresh an embedding row with the active model."""
    if not is_available():
        return {"status": "skipped", "reason": "unavailable"}
    if not text or not text.strip():
        return {"status": "skipped", "reason": "empty_text"}

    name = model_name or active_model_name()
    text_hash = _compute_text_hash(text)
    try:
        existing = conn.execute(
            "SELECT id, text_hash, model_name FROM embeddings "
            "WHERE source_table = ? AND source_id = ?",
            (source_table, source_id),
        ).fetchone()
    except sqlite3.OperationalError as exc:
        return {"status": "skipped", "reason": f"table_missing: {exc}"}

    if existing and existing[1] == text_hash and existing[2] == name:
        return {"status": "unchanged", "id": existing[0]}

    vector = embed_text(text, model_name=name)
    if vector is None:
        return {"status": "skipped", "reason": "embed_failed"}
    dim = bytes_to_dim(vector) or model_dim(name) or EMBEDDING_DIM

    try:
        # Use embedding_dim column when the v12 migration is applied;
        # fall back to the three-column insert for pre-v12 DBs.
        has_dim_col = _has_embedding_dim_column(conn)
        if existing:
            if has_dim_col:
                conn.execute(
                    "UPDATE embeddings SET text_hash = ?, embedding = ?, "
                    "model_name = ?, embedding_dim = ?, created_at = CURRENT_TIMESTAMP "
                    "WHERE id = ?",
                    (text_hash, vector, name, dim, existing[0]),
                )
            else:
                conn.execute(
                    "UPDATE embeddings SET text_hash = ?, embedding = ?, "
                    "model_name = ?, created_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (text_hash, vector, name, existing[0]),
                )
            conn.commit()
            return {"status": "updated", "id": existing[0], "dim": dim, "model_name": name}

        if has_dim_col:
            cursor = conn.execute(
                "INSERT INTO embeddings (source_table, source_id, text_hash, "
                "embedding, model_name, embedding_dim) VALUES (?, ?, ?, ?, ?, ?)",
                (source_table, source_id, text_hash, vector, name, dim),
            )
        else:
            cursor = conn.execute(
                "INSERT INTO embeddings (source_table, source_id, text_hash, "
                "embedding, model_name) VALUES (?, ?, ?, ?, ?)",
                (source_table, source_id, text_hash, vector, name),
            )
        conn.commit()
        return {"status": "inserted", "id": cursor.lastrowid, "dim": dim, "model_name": name}
    except sqlite3.OperationalError as exc:
        return {"status": "error", "reason": str(exc)}


def _has_embedding_dim_column(conn: sqlite3.Connection) -> bool:
    """Tolerate pre-v12 DBs that lack the embedding_dim column."""
    try:
        rows = conn.execute("PRAGMA table_info(embeddings)").fetchall()
    except sqlite3.OperationalError:
        return False
    return any(r[1] == "embedding_dim" for r in rows)


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

    query_vec = embed_text(query)
    if query_vec is None:
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
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.OperationalError as exc:
        logger.warning("search_similar query failed: %s", exc)
        return []

    if not rows:
        return []

    candidate_vecs = [r[2] for r in rows]
    scores = cosine_similarity(query_vec, candidate_vecs)
    if not scores:
        return []

    # Build (row, score) pairs, filter by threshold, sort, take top N
    scored = [
        {"source_table": rows[i][0], "source_id": rows[i][1], "score": scores[i]}
        for i in range(len(rows))
        if scores[i] >= threshold
    ]
    scored.sort(key=lambda d: d["score"], reverse=True)
    return scored[:limit]


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
        ("observations", "SELECT id, title, narrative, concepts FROM observations",
         lambda r: " ".join(filter(None, [r["title"], r["narrative"], r["concepts"]]))),
        ("learned_patterns", "SELECT id, pattern, concepts FROM learned_patterns",
         lambda r: " ".join(filter(None, [r["pattern"], r["concepts"]]))),
        ("outcome_history", "SELECT id, narrative_key_insight, narrative_what_failed, narrative_what_worked FROM outcome_history",
         lambda r: " ".join(filter(None, [r["narrative_key_insight"], r["narrative_what_failed"], r["narrative_what_worked"]]))),
        ("document_chunks", "SELECT id, heading_path, content FROM document_chunks",
         lambda r: " ".join(filter(None, [r["heading_path"], r["content"]]))),
    ]

    for table, query, text_builder in handlers:
        stats = {"processed": 0, "inserted": 0, "updated": 0, "unchanged": 0, "skipped": 0}
        try:
            rows = conn.execute(query).fetchall()
        except sqlite3.OperationalError:
            # Table doesn't exist yet (e.g. document_chunks before v5)
            report[table] = stats
            continue
        for row in rows:
            stats["processed"] += 1
            text = text_builder(row)
            result = upsert_embedding(conn, table, row["id"], text)
            status = result.get("status", "skipped")
            if status == "inserted":
                stats["inserted"] += 1
            elif status == "updated":
                stats["updated"] += 1
            elif status == "unchanged":
                stats["unchanged"] += 1
            else:
                stats["skipped"] += 1
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
    parser.add_argument("--reindex", action="store_true", help="Re-embed all rows in supported tables")
    parser.add_argument("--db", type=str, default=None, help="Override DB path (defaults to COS_DB_PATH)")
    args = parser.parse_args()

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from db import init_db

    if not is_available():
        print("ERROR: sentence-transformers not installed. Run: uv sync --extra rag", file=sys.stderr)
        sys.exit(1)

    conn = init_db(args.db)
    if args.reindex:
        result = reindex_all(conn)
        print(json.dumps(result, indent=2))
    else:
        from db import get_db_stats
        stats = get_db_stats(conn)
        print(json.dumps({"status": "ok", "embeddings_available": True, "db_stats": stats}, indent=2))
    conn.close()


if __name__ == "__main__":
    _main()
