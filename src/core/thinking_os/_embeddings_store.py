"""Row store: text hashing for staleness, and the embedding upsert path.

Private module of embeddings.py — import through that facade.
"""

from __future__ import annotations

import hashlib
import sqlite3

# Loaded flat as `embeddings` by thinking_os and as `thinking_os.embeddings`
# by graph_os; the relative form has no parent package under the first.
try:
    from ._embeddings_model import embed_text, is_available
    from ._embeddings_registry import (
        EMBEDDING_DIM,
        active_model_name,
        bytes_to_dim,
        model_dim,
    )
except ImportError:  # pragma: no cover
    from _embeddings_model import (  # type: ignore[no-redef]
        embed_text,
        is_available,
    )
    from _embeddings_registry import (  # type: ignore[no-redef]
        EMBEDDING_DIM,
        active_model_name,
        bytes_to_dim,
        model_dim,
    )

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

    try:
        status, row_id, dim = _persist_embedding(
            conn,
            source_table,
            source_id,
            text_hash,
            vector,
            name,
            existing[0] if existing else None,
            _has_embedding_dim_column(conn),
        )
        conn.commit()
        return {"status": status, "id": row_id, "dim": dim, "model_name": name}
    except sqlite3.OperationalError as exc:
        return {"status": "error", "reason": str(exc)}


def _persist_embedding(
    conn: sqlite3.Connection,
    source_table: str,
    source_id: int,
    text_hash: str,
    vector: bytes,
    name: str,
    existing_id: int | None,
    has_dim_col: bool,
) -> tuple[str, int, int]:
    """Write one embedding row (INSERT or UPDATE). Caller commits.

    Shared by upsert_embedding (single) and reindex_all (batched). Returns
    (status, row_id, dim). `has_dim_col` tolerates pre-v12 DBs missing the
    embedding_dim column.
    """
    dim = bytes_to_dim(vector) or model_dim(name) or EMBEDDING_DIM
    if existing_id is not None:
        if has_dim_col:
            conn.execute(
                "UPDATE embeddings SET text_hash = ?, embedding = ?, model_name = ?, "
                "embedding_dim = ?, created_at = CURRENT_TIMESTAMP WHERE id = ?",
                (text_hash, vector, name, dim, existing_id),
            )
        else:
            conn.execute(
                "UPDATE embeddings SET text_hash = ?, embedding = ?, model_name = ?, "
                "created_at = CURRENT_TIMESTAMP WHERE id = ?",
                (text_hash, vector, name, existing_id),
            )
        return "updated", existing_id, dim

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
    return "inserted", int(cursor.lastrowid), dim


def _has_embedding_dim_column(conn: sqlite3.Connection) -> bool:
    """Tolerate pre-v12 DBs that lack the embedding_dim column."""
    try:
        rows = conn.execute("PRAGMA table_info(embeddings)").fetchall()
    except sqlite3.OperationalError:
        return False
    return any(r[1] == "embedding_dim" for r in rows)
