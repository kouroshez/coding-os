"""The durable embedding outbox: enqueue off the hot path, drain off the interactive one.

One reason to change: how work deferred by the capture path is queued and retried.
Split out of embeddings.py, which owns computing and searching vectors — a
different concern on a different schedule.
"""

from __future__ import annotations

import logging
import sqlite3
import time

logger = logging.getLogger("thinking_os.embeddings")


def _embeddings():
    # Resolved through the MODULE, never by value: tests monkeypatch
    # `embeddings.is_available`, and a name bound at import time here would keep
    # pointing at the original function and silently ignore the patch.
    try:  # package import
        from . import embeddings
    except ImportError:  # flat import — hooks and the MCP server put this dir on sys.path
        import embeddings  # type: ignore[no-redef]
    return embeddings


def enqueue_outbox(conn: sqlite3.Connection, source_table: str, source_id: int) -> bool:
    """Record that (source_table, source_id) needs an embedding, off the hot path.

    Idempotent via UNIQUE(source_table, source_id) — re-enqueueing is a no-op.
    Cheap (one INSERT, no model load) so the capture hot path stays fast.
    """
    try:
        conn.execute(
            "INSERT OR IGNORE INTO embedding_outbox (source_table, source_id, enqueued_at) "
            "VALUES (?, ?, ?)",
            (source_table, int(source_id), int(time.time())),
        )
        conn.commit()
        return True
    except sqlite3.OperationalError as exc:
        logger.debug("outbox enqueue skipped (%s): %s", source_table, exc)
        return False


def drain_outbox(conn: sqlite3.Connection, *, limit: int = 128, max_attempts: int = 3) -> dict:
    """Embed up to `limit` pending outbox rows; remove on success, retry-bounded.

    Runs off the interactive path (Stop hook / cron). A row whose source text
    is gone is dropped; a transient embed failure increments attempts and keeps
    last_error, and is abandoned after max_attempts so the queue can't wedge.
    """
    # Self-heal: drop outbox rows already satisfied by an embedding (any path may
    # have embedded them). Model-free, so it runs even when the encoder is down —
    # otherwise these rows leak in the queue forever.
    try:
        conn.execute(
            "DELETE FROM embedding_outbox WHERE EXISTS ("
            "SELECT 1 FROM embeddings e WHERE e.source_table = embedding_outbox.source_table "
            "AND e.source_id = embedding_outbox.source_id)"
        )
        conn.commit()
    except sqlite3.OperationalError as exc:
        logger.debug("outbox reconcile skipped (no table?): %s", exc)
    if not _embeddings().is_available():
        return {"status": "unavailable", "drained": 0, "failed": 0, "remaining": 0}
    try:
        rows = conn.execute(
            "SELECT id, source_table, source_id FROM embedding_outbox "
            "WHERE attempts < ? ORDER BY attempts, enqueued_at LIMIT ?",
            (int(max_attempts), max(1, int(limit))),
        ).fetchall()
    except sqlite3.OperationalError as exc:
        logger.debug("outbox drain skipped (no table?): %s", exc)
        return {"status": "no_table", "drained": 0, "failed": 0, "remaining": 0}
    if not rows:
        return {"status": "ok", "drained": 0, "failed": 0, "remaining": 0}

    # Reuse the migrator's per-table text reconstruction (single source of truth
    # for "how to rebuild the text behind an embedding"). Lazy import avoids the
    # embeddings<->migrator circular import at module load.
    from migrator_embeddings import _text_for_row  # type: ignore

    drained = failed = dropped = 0
    for oid, source_table, source_id in rows:
        text = _text_for_row(conn, {"source_table": source_table, "source_id": source_id})
        if not text:
            # Source row is gone (reaped by the TTL). Counted, not silent: a batch
            # of pure orphans used to return drained=0/failed=0, which every
            # caller reads as "nothing to do" rather than "the queue is starving".
            conn.execute("DELETE FROM embedding_outbox WHERE id = ?", (oid,))
            dropped += 1
            continue
        res = _embeddings().upsert_embedding(conn, source_table, int(source_id), text)
        if res.get("status") in ("inserted", "updated", "unchanged"):
            conn.execute("DELETE FROM embedding_outbox WHERE id = ?", (oid,))
            drained += 1
        else:
            conn.execute(
                "UPDATE embedding_outbox SET attempts = attempts + 1, last_error = ? WHERE id = ?",
                (str(res.get("reason"))[:200], oid),
            )
            failed += 1
    conn.commit()
    remaining = conn.execute(
        "SELECT COUNT(*) FROM embedding_outbox WHERE attempts < ?", (int(max_attempts),)
    ).fetchone()[0]
    return {
        "status": "ok",
        "drained": drained,
        "failed": failed,
        "dropped": dropped,
        "remaining": int(remaining),
    }
