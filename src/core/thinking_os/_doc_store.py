"""Chunk persistence for the document RAG index.

Row lifecycle only — mtime lookup, per-path and orphan deletion, and the
fire-and-forget embedding write whose failure must never fail an index run.
"""

from __future__ import annotations

import logging
import sqlite3

logger = logging.getLogger("coding_os.doc_indexer")


def _get_max_mtime(conn: sqlite3.Connection, source_path: str) -> int | None:
    """Return the maximum mtime stored for `source_path`, or None if no rows."""
    row = conn.execute(
        "SELECT MAX(mtime) FROM document_chunks WHERE source_path = ?",
        (source_path,),
    ).fetchone()
    return row[0] if row and row[0] is not None else None


def _delete_chunks_for_path(conn: sqlite3.Connection, source_path: str) -> None:
    """Delete all chunks (and their embeddings) for the given source path."""
    chunk_ids = [
        r[0]
        for r in conn.execute(
            "SELECT id FROM document_chunks WHERE source_path = ?", (source_path,)
        ).fetchall()
    ]
    if not chunk_ids:
        return
    placeholders = ",".join("?" * len(chunk_ids))
    conn.execute(
        f"DELETE FROM embeddings WHERE source_table = 'document_chunks' AND source_id IN ({placeholders})",
        chunk_ids,
    )
    conn.execute("DELETE FROM document_chunks WHERE source_path = ?", (source_path,))


def _delete_orphaned_chunks(conn: sqlite3.Connection, seen_paths: set[str]) -> int:
    """Delete chunks for files that are no longer in the configured sources.

    Args:
        conn: SQLite connection.
        seen_paths: Set of source_path strings that ARE still present.

    Returns:
        Count of files whose chunks were deleted.
    """
    existing = {
        r[0] for r in conn.execute("SELECT DISTINCT source_path FROM document_chunks").fetchall()
    }
    orphaned = existing - seen_paths
    for path in orphaned:
        _delete_chunks_for_path(conn, path)
    return len(orphaned)


def _embed_chunk_safe(
    conn: sqlite3.Connection,
    chunk_id: int,
    heading_path: str,
    content: str,
) -> None:
    """Embed a document chunk. Errors logged at debug level only."""
    try:
        from embeddings import upsert_embedding
    except ImportError as exc:
        logger.debug("Skipping chunk embedding (module unavailable): %s", exc)
        return
    try:
        text_to_embed = " ".join(filter(None, [heading_path, content]))
        upsert_embedding(conn, "document_chunks", chunk_id, text_to_embed)
    except sqlite3.OperationalError as exc:
        logger.debug("Skipping chunk embedding (table missing): %s", exc)
    except Exception as exc:  # pragma: no cover
        logger.debug("Skipping chunk embedding (unexpected): %s", exc)
