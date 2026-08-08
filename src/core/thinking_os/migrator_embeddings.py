"""thinking_os — background embedding migrator.

DEPENDS:  embeddings.py (encoder + dim helpers), db.py migration v12
          (`embedding_dim` column).
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import embeddings

logger = logging.getLogger("coding_os.migrator_embeddings")

DEFAULT_BATCH_SIZE = 256
DEFAULT_TARGET_MODEL = "BAAI/bge-m3"
DEFAULT_CHECKPOINT = ".coding-os/.embedding-migration.json"


@dataclass
class MigrationCheckpoint:
    """On-disk progress marker — survives crash / SIGTERM."""

    target_model: str = DEFAULT_TARGET_MODEL
    total: int = 0
    done: int = 0
    last_id: int = 0
    eta_seconds: float = 0.0
    started_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    @classmethod
    def load(cls, path: str | Path) -> MigrationCheckpoint:
        p = Path(path)
        if not p.exists():
            return cls()
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("checkpoint load failed (%s); starting fresh", exc)
            return cls()
        return cls(
            target_model=data.get("target_model", DEFAULT_TARGET_MODEL),
            total=int(data.get("total", 0)),
            done=int(data.get("done", 0)),
            last_id=int(data.get("last_id", 0)),
            eta_seconds=float(data.get("eta_seconds", 0.0)),
            started_at=float(data.get("started_at", time.time())),
            updated_at=float(data.get("updated_at", time.time())),
        )

    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        self.updated_at = time.time()
        # Atomic replace — partial writes never corrupt the checkpoint.
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        tmp.replace(p)


# ---------------------------------------------------------------------------
# Work selection
# ---------------------------------------------------------------------------


def _pick_pending_rows(
    conn: sqlite3.Connection,
    *,
    target_model: str,
    last_id: int,
    batch_size: int,
) -> list[sqlite3.Row]:
    """Return rows whose model is not yet the target, after last_id."""
    conn.row_factory = sqlite3.Row
    return conn.execute(
        """
        SELECT id, source_table, source_id, text_hash, model_name
        FROM embeddings
        WHERE (model_name IS NULL OR model_name != ?) AND id > ?
        ORDER BY id ASC
        LIMIT ?
        """,
        (target_model, int(last_id), int(batch_size)),
    ).fetchall()


def _text_for_row(conn: sqlite3.Connection, row: sqlite3.Row) -> str | None:
    """Reconstruct the source text the old embedding was computed from."""
    table = row["source_table"]
    source_id = int(row["source_id"])

    # Table-specific text columns mirror reindex_all in embeddings.py.
    # Missing / malformed tables are tolerated — we simply skip the row.
    queries: dict[str, tuple[str, tuple[str, ...]]] = {
        "observations": (
            "SELECT title, narrative, concepts FROM observations WHERE id = ?",
            ("title", "narrative", "concepts"),
        ),
        "learned_patterns": (
            "SELECT pattern, concepts FROM learned_patterns WHERE id = ?",
            ("pattern", "concepts"),
        ),
        "outcome_history": (
            "SELECT narrative_key_insight, narrative_what_failed, "
            "narrative_what_worked FROM outcome_history WHERE id = ?",
            (
                "narrative_key_insight",
                "narrative_what_failed",
                "narrative_what_worked",
            ),
        ),
        "document_chunks": (
            "SELECT heading_path, content FROM document_chunks WHERE id = ?",
            ("heading_path", "content"),
        ),
        "tasks": (
            "SELECT title, goal_text, requirements FROM tasks WHERE id = ?",
            ("title", "goal_text", "requirements"),
        ),
        # graph_nodes embeddings (Wave 1) — without this the migrator silently
        # skips every code-symbol vector (returns None → never re-embedded),
        # leaving the graph half-migrated. Mirrors embeddings.reindex_all.
        "graph_nodes": (
            "SELECT label, signature, doc_blob FROM graph_nodes WHERE id = ?",
            ("label", "signature", "doc_blob"),
        ),
    }
    handler = queries.get(table)
    if handler is None:
        return None
    sql, fields = handler
    try:
        record = conn.execute(sql, (source_id,)).fetchone()
    except sqlite3.OperationalError:
        return None
    if record is None:
        return None
    parts = [record[i] for i in range(len(fields))]
    cleaned = " ".join(p for p in parts if p)
    return cleaned or None


# ---------------------------------------------------------------------------
# Batch execution
# ---------------------------------------------------------------------------


def _total_pending(conn: sqlite3.Connection, target_model: str) -> int:
    row = conn.execute(
        "SELECT COUNT(*) FROM embeddings WHERE model_name IS NULL OR model_name != ?",
        (target_model,),
    ).fetchone()
    return int(row[0]) if row else 0


def run_one_batch(
    conn: sqlite3.Connection,
    *,
    target_model: str = DEFAULT_TARGET_MODEL,
    batch_size: int = DEFAULT_BATCH_SIZE,
    checkpoint_path: str | Path = DEFAULT_CHECKPOINT,
) -> dict:
    """Process one batch; persist checkpoint; return status dict."""
    checkpoint = MigrationCheckpoint.load(checkpoint_path)
    if checkpoint.target_model != target_model:
        checkpoint = MigrationCheckpoint(target_model=target_model)

    total = _total_pending(conn, target_model) + checkpoint.done
    checkpoint.total = total
    if total == 0 or checkpoint.done >= total:
        checkpoint.save(checkpoint_path)
        return {
            "done": checkpoint.done,
            "total": total,
            "migrated_this_batch": 0,
            "remaining": max(total - checkpoint.done, 0),
            "target_model": target_model,
            "eta_seconds": 0.0,
            "stopped_reason": "idle",
        }

    rows = _pick_pending_rows(
        conn,
        target_model=target_model,
        last_id=checkpoint.last_id,
        batch_size=batch_size,
    )
    if not rows:
        # Nothing left above last_id — reset cursor and retry in case we
        # wrapped after a partial earlier pass.
        checkpoint.last_id = 0
        rows = _pick_pending_rows(
            conn,
            target_model=target_model,
            last_id=0,
            batch_size=batch_size,
        )

    started = time.time()
    migrated = 0
    for row in rows:
        text = _text_for_row(conn, row)
        if text is None:
            # Row references a gone/empty source row — mark it processed
            # by nudging last_id forward so we don't retry it forever.
            checkpoint.last_id = max(checkpoint.last_id, int(row["id"]))
            continue
        status = embeddings.upsert_embedding(
            conn,
            row["source_table"],
            int(row["source_id"]),
            text,
            model_name=target_model,
        )
        if status.get("status") in ("inserted", "updated", "unchanged"):
            migrated += 1
            checkpoint.last_id = max(checkpoint.last_id, int(row["id"]))

    elapsed = time.time() - started
    checkpoint.done += migrated
    remaining = max(total - checkpoint.done, 0)
    if migrated and elapsed > 0:
        # Simple EMA-ish smoothing: blend fresh estimate with previous.
        fresh_eta = (elapsed / migrated) * remaining
        checkpoint.eta_seconds = (
            (checkpoint.eta_seconds * 0.5 + fresh_eta * 0.5)
            if checkpoint.eta_seconds
            else fresh_eta
        )
    checkpoint.save(checkpoint_path)

    return {
        "done": checkpoint.done,
        "total": total,
        "migrated_this_batch": migrated,
        "remaining": remaining,
        "target_model": target_model,
        "eta_seconds": round(checkpoint.eta_seconds, 1),
        "stopped_reason": "batch_done",
    }


def migration_status(
    conn: sqlite3.Connection,
    *,
    target_model: str = DEFAULT_TARGET_MODEL,
    checkpoint_path: str | Path = DEFAULT_CHECKPOINT,
) -> dict:
    """Read-only: report current migration state."""
    checkpoint = MigrationCheckpoint.load(checkpoint_path)
    pending = _total_pending(conn, target_model)
    done = checkpoint.done
    total = max(done + pending, checkpoint.total)
    complete = pending == 0
    return {
        "done": done,
        "total": total,
        "remaining": pending,
        "target_model": target_model,
        "migration_complete": complete,
        "eta_seconds": round(checkpoint.eta_seconds, 1),
        "started_at": checkpoint.started_at,
        "updated_at": checkpoint.updated_at,
    }


def run_until_idle(
    conn: sqlite3.Connection,
    *,
    target_model: str = DEFAULT_TARGET_MODEL,
    batch_size: int = DEFAULT_BATCH_SIZE,
    checkpoint_path: str | Path = DEFAULT_CHECKPOINT,
    max_batches: int | None = None,
) -> dict:
    """Synchronous driver — for tests and manual runs only."""
    if not embeddings.is_available():
        return {
            "status": "skipped",
            "reason": "unavailable",
            "target_model": target_model,
        }

    iterations = 0
    last: dict[str, Any] = {}
    while True:
        last = run_one_batch(
            conn,
            target_model=target_model,
            batch_size=batch_size,
            checkpoint_path=checkpoint_path,
        )
        iterations += 1
        if last["migrated_this_batch"] == 0 or last["remaining"] == 0:
            break
        if max_batches is not None and iterations >= max_batches:
            last["stopped_reason"] = "max_batches"
            break
    last["batches_executed"] = iterations
    return last


__all__ = [
    "DEFAULT_BATCH_SIZE",
    "DEFAULT_CHECKPOINT",
    "DEFAULT_TARGET_MODEL",
    "MigrationCheckpoint",
    "migration_status",
    "run_one_batch",
    "run_until_idle",
]
