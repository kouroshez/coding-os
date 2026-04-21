"""
Coding OS — Retrieval audit + outcome feedback loop (Phase G.8).

Every MCP retrieval tool (`cos_search`, `cos_doc_search`, `cos_task_search`)
calls `log_retrieval` after producing results. The row sits in `retrievals`
with `outcome=NULL` until the active task completes; the `task-done` hook
back-fills `outcome` and `outcome_at` via `backfill_task_outcome`.

Nightly (or on-demand) `learn_from_retrievals` walks recent retrievals and
adjusts `document_chunks.priority`:
  - chunk cited in a task that succeeded        → priority += 0.02
  - chunk cited in a task that reworked/blocked → priority -= 0.01
  - passive retrieval (not cited) has weaker effect  ±0.005
Priority is clamped to [0.1, 0.9] so one run can never drive a source
all the way to zero or one.

Public surface:
    log_retrieval(conn, *, layer, query, rows, task_id=None)
    cite_retrievals(conn, retrieval_ids)
    backfill_task_outcome(conn, task_id, outcome)
    learn_from_retrievals(conn, *, lookback_days=7, dry_run=False)

All functions are read-tolerant: missing tables (pre-v10) return clean
empty/zero results instead of raising.
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Iterable, Optional

logger = logging.getLogger("coding_os.tools.retrieve")

_PRIORITY_MIN = 0.1
_PRIORITY_MAX = 0.9

# Delta per retrieval outcome. Cited retrievals carry roughly 4× weight
# vs passive — matching how the agent cite signal is the honest "I used this".
_DELTA_CITED_SUCCESS = 0.02
_DELTA_CITED_FAIL = -0.01
_DELTA_PASSIVE_SUCCESS = 0.005
_DELTA_PASSIVE_FAIL = -0.0025

# Outcome categories mapped to signal direction. Anything not in these sets
# is ignored (e.g. NULL, "wip") — priority only moves when there is a verdict.
_SUCCESS_OUTCOMES = frozenset({"success", "done"})
_FAIL_OUTCOMES = frozenset({"rework", "blocked", "failed"})


def _has_retrievals(conn: sqlite3.Connection) -> bool:
    try:
        conn.execute("SELECT 1 FROM retrievals LIMIT 1")
        return True
    except sqlite3.OperationalError:
        return False


def _read_session_id() -> str:
    """Return the active session id (or 'ses-unknown'). Mirrors the resolution
    order documented in capture._read_session_id and core/hooks/cos-env.sh
    (Rule 1) — agent-agnostic, never reads .claude/."""
    import os
    from pathlib import Path
    state_dir = Path(os.environ.get("COS_STATE_DIR", ".coding-os"))
    # Priority 1 — explicit COS_AGENT_DIR
    agent_dir_env = os.environ.get("COS_AGENT_DIR")
    if agent_dir_env:
        f = Path(agent_dir_env) / "session-id"
        if f.exists():
            sid = f.read_text().strip()
            if sid:
                return sid
    # Priority 2 — derived from COS_AGENT / .agent marker
    agent = os.environ.get("COS_AGENT", "")
    if not agent:
        marker = state_dir / ".agent"
        if marker.exists():
            agent = marker.read_text().strip()
    if agent:
        f = state_dir / agent / "session-id"
        if f.exists():
            sid = f.read_text().strip()
            if sid:
                return sid
    # Priority 3 — pre-Phase-I flat layout (kept for first-run migration only)
    flat = state_dir / "session-id"
    if flat.exists():
        sid = flat.read_text().strip()
        if sid:
            return sid
    return "ses-unknown"


def _read_current_task() -> Optional[str]:
    """Return the active task id/slug from agent-private state, or None.
    Same resolution order as _read_session_id."""
    import os
    from pathlib import Path
    state_dir = Path(os.environ.get("COS_STATE_DIR", ".coding-os"))
    candidates: list[Path] = []
    agent_dir_env = os.environ.get("COS_AGENT_DIR")
    if agent_dir_env:
        candidates.append(Path(agent_dir_env) / ".task-current")
    agent = os.environ.get("COS_AGENT", "")
    if not agent:
        marker = state_dir / ".agent"
        if marker.exists():
            agent = marker.read_text().strip()
    if agent:
        candidates.append(state_dir / agent / ".task-current")
    candidates.append(state_dir / ".task-current")
    for f in candidates:
        if f.exists():
            v = f.read_text().strip()
            if v:
                return v
    return None


def log_retrieval(
    conn: sqlite3.Connection,
    *,
    layer: str,
    query: str,
    rows: Iterable[dict],
    task_id: Optional[str] = None,
) -> list[int]:
    """Append one retrievals row per returned result. Fire-and-forget.

    PURPOSE:      Anchor every MCP retrieval so priority learning can later
                  correlate rows with the task they supported.
    INPUT:        conn, layer name, user query, rows returned by the search,
                  optional explicit task_id (falls back to `.task-current`).
    OUTPUT:       list of inserted retrieval row ids (empty if pre-v10 or
                  rows empty).
    DEPENDENCIES: retrievals (v10+).
    NOTES:        Each row dict must carry at least `source_table` + `id`
                  (or `source_id`) + optional `score`. Row shapes that don't
                  expose an id are silently skipped — we never raise from
                  the logger path.
    """
    if not rows:
        return []
    if not _has_retrievals(conn):
        return []

    session_id = _read_session_id()
    tid = task_id or _read_current_task()

    inserted: list[int] = []
    for row in rows:
        source_table = row.get("source_table") or _infer_source_table(row, layer)
        source_id = row.get("source_id") or row.get("id")
        if source_table is None or source_id is None:
            continue
        try:
            cur = conn.execute(
                "INSERT INTO retrievals "
                "(session_id, task_id, layer, query, source_table, source_id, score) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (session_id, tid, layer, query, source_table,
                 int(source_id), float(row.get("score", 0.0))),
            )
            inserted.append(cur.lastrowid)
        except sqlite3.OperationalError as exc:
            logger.debug("log_retrieval skipped row: %s", exc)
            continue
    try:
        conn.commit()
    except sqlite3.OperationalError:
        pass
    return inserted


def _infer_source_table(row: dict, layer: str) -> Optional[str]:
    """Best-effort source_table inference for rows that don't carry it.

    - doc_search rows have `source_path` + `source_type`  → document_chunks
    - task rows have `task_id` + `domain`                 → tasks
    - memory rows should already carry `source_table`
    """
    if "source_path" in row or layer == "docs":
        return "document_chunks"
    if "task_id" in row or layer == "tasks":
        return "tasks"
    return None


def cite_retrievals(
    conn: sqlite3.Connection, retrieval_ids: list[int],
) -> dict:
    """Mark retrievals as actively cited by the agent.

    PURPOSE:      Honest signal that the agent used the retrieved row.
                  Priority learning weights cited retrievals ~4× stronger
                  than passive ones.
    INPUT:        list of retrieval row ids.
    OUTPUT:       {"updated": N, "unknown": [...]}.
    DEPENDENCIES: retrievals (v10+).
    NOTES:        Idempotent — re-citing has no extra effect; the flag is
                  a set bit not a counter.
    """
    if not _has_retrievals(conn):
        return {"updated": 0, "unknown": retrieval_ids}
    if not retrieval_ids:
        return {"updated": 0, "unknown": []}

    placeholders = ",".join("?" * len(retrieval_ids))
    existing = {
        r[0] for r in conn.execute(
            f"SELECT id FROM retrievals WHERE id IN ({placeholders})",
            retrieval_ids,
        ).fetchall()
    }
    unknown = [rid for rid in retrieval_ids if rid not in existing]
    if existing:
        ph = ",".join("?" * len(existing))
        conn.execute(
            f"UPDATE retrievals SET was_cited = 1 WHERE id IN ({ph})",
            list(existing),
        )
        conn.commit()
    return {"updated": len(existing), "unknown": unknown}


def backfill_task_outcome(
    conn: sqlite3.Connection, task_id: str, outcome: str,
) -> int:
    """Back-fill `outcome` and `outcome_at` for all retrievals of a task.

    PURPOSE:      Close the feedback loop — `task-done` hook calls this so
                  priority learning can read (retrieval, outcome) pairs.
    INPUT:        task_id string, outcome label ("success", "rework", ...).
    OUTPUT:       count of rows updated.
    DEPENDENCIES: retrievals (v10+).
    NOTES:        No-op on pre-v10 DBs. Existing outcome values are NOT
                  overwritten (append-only intent) — first outcome wins.
    """
    if not _has_retrievals(conn):
        return 0
    cur = conn.execute(
        "UPDATE retrievals SET outcome = ?, outcome_at = CURRENT_TIMESTAMP "
        "WHERE task_id = ? AND outcome IS NULL",
        (outcome, task_id),
    )
    conn.commit()
    return cur.rowcount or 0


def learn_from_retrievals(
    conn: sqlite3.Connection,
    *,
    lookback_days: int = 7,
    dry_run: bool = False,
) -> dict:
    """Adjust document_chunks.priority based on retrieval outcomes.

    PURPOSE:      Make priority reflect empirical usefulness instead of a
                  static rag-config number.
    INPUT:        lookback window in days; dry_run=True reports changes
                  without writing.
    OUTPUT:       {"adjusted": N, "gained": M, "lost": K, "changes": [...]}.
    DEPENDENCIES: retrievals, document_chunks (v10+).
    NOTES:        - Only document_chunks rows are adjusted in this pass;
                    other source_tables are logged but not mutated (their
                    priority concept is less central).
                  - Per-chunk delta is the SUM of individual retrieval
                    signals, then clamped — protects against single-run
                    cliff jumps on heavily retrieved chunks.
    """
    if not _has_retrievals(conn):
        return {"adjusted": 0, "gained": 0, "lost": 0, "changes": [],
                "status": "pre_v10_no_op"}

    rows = conn.execute(
        "SELECT source_id, was_cited, outcome "
        "FROM retrievals "
        "WHERE source_table = 'document_chunks' "
        "  AND outcome IS NOT NULL "
        "  AND created_at >= datetime('now', '-' || ? || ' days')",
        (int(lookback_days),),
    ).fetchall()

    if not rows:
        return {"adjusted": 0, "gained": 0, "lost": 0, "changes": [],
                "status": "no_data"}

    delta_by_chunk: dict[int, float] = {}
    for r in rows:
        outcome = (r["outcome"] or "").lower()
        cited = bool(r["was_cited"])
        if outcome in _SUCCESS_OUTCOMES:
            step = _DELTA_CITED_SUCCESS if cited else _DELTA_PASSIVE_SUCCESS
        elif outcome in _FAIL_OUTCOMES:
            step = _DELTA_CITED_FAIL if cited else _DELTA_PASSIVE_FAIL
        else:
            continue
        delta_by_chunk[r["source_id"]] = delta_by_chunk.get(r["source_id"], 0.0) + step

    if not delta_by_chunk:
        return {"adjusted": 0, "gained": 0, "lost": 0, "changes": [],
                "status": "no_effective_signal"}

    placeholders = ",".join("?" * len(delta_by_chunk))
    current = {
        r["id"]: r["priority"]
        for r in conn.execute(
            f"SELECT id, priority FROM document_chunks WHERE id IN ({placeholders})",
            list(delta_by_chunk.keys()),
        ).fetchall()
    }

    changes: list[dict] = []
    gained = lost = 0
    for chunk_id, delta in delta_by_chunk.items():
        prev = current.get(chunk_id)
        if prev is None:
            continue  # chunk deleted between retrieval and now
        new = max(_PRIORITY_MIN, min(_PRIORITY_MAX, prev + delta))
        if abs(new - prev) < 1e-9:
            continue
        changes.append({
            "chunk_id": chunk_id,
            "old": round(prev, 4),
            "new": round(new, 4),
            "delta": round(delta, 4),
        })
        if new > prev:
            gained += 1
        else:
            lost += 1

        if not dry_run:
            conn.execute(
                "UPDATE document_chunks SET priority = ? WHERE id = ?",
                (new, chunk_id),
            )

    if not dry_run:
        conn.commit()

    return {
        "adjusted": len(changes),
        "gained": gained,
        "lost": lost,
        "changes": changes,
        "status": "dry_run" if dry_run else "applied",
    }
