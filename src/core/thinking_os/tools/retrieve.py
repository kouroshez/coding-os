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
from collections.abc import Iterable
from typing import Optional

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


_TASK_ID_PATTERN = __import__("re").compile(r"\bTASK-\d+\b")


def _normalize_task_id(raw: str) -> str:
    """Extract a canonical task identifier from a `.task-current` payload."""
    if not raw:
        return raw
    s = raw.strip()
    m = _TASK_ID_PATTERN.search(s)
    if m:
        return m.group(0)
    parts = s.split(maxsplit=1)
    if parts and parts[0].startswith("ses-") and len(parts) > 1:
        return parts[1].strip()
    return s


def _read_current_task() -> str | None:
    """Return the active task id/slug from agent-private state, or None.
    Same resolution order as _read_session_id.  Always canonicalizes
    through _normalize_task_id so `retrievals.task_id` stays consistent
    across writers (plain TASK-NNN when the marker carries one)."""
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
                return _normalize_task_id(v)
    return None


def log_retrieval(
    conn: sqlite3.Connection,
    *,
    layer: str,
    query: str,
    rows: Iterable[dict],
    task_id: str | None = None,
) -> list[int]:
    """Append one retrievals row per returned result. Fire-and-forget."""
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
                (
                    session_id,
                    tid,
                    layer,
                    query,
                    source_table,
                    int(source_id),
                    float(row.get("score", 0.0)),
                ),
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


def _infer_source_table(row: dict, layer: str) -> str | None:
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


def _has_router_log(conn: sqlite3.Connection) -> bool:
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='retrieval_router_log'"
        ).fetchone()
    except sqlite3.Error:
        return False
    return row is not None


_IDENTIFIER_QUERY_RE = __import__("re").compile(
    r"[A-Za-z_][A-Za-z0-9_]{1,}\(\)|[a-z]+(?:_[a-z0-9]+)+|"
    r"[A-Z][a-z0-9]+[A-Z][A-Za-z0-9]+|TASK-\d+|`[^`]+`|[\w]+\.(py|ts|tsx|md|go|sh)\b"
)


def _classify_query_shape(query: str) -> str:
    """Return a coarse shape label for retrieval_router_log.

    Three buckets — keep it small so the column stays groupable:
      - identifier  : code-shaped (snake_case / CamelCase / file path)
      - task_id     : raw TASK-NNN reference
      - natural     : everything else (free-text)
    """
    q = (query or "").strip()
    if not q:
        return "empty"
    if _IDENTIFIER_QUERY_RE.search(q):
        return "task_id" if "TASK-" in q else "identifier"
    return "natural"


def log_router_decision(
    conn: sqlite3.Connection,
    *,
    query: str,
    chosen_layer: str,
    confidence: float = 1.0,
    fanout_layers: list[str] | None = None,
    bytes_returned: int = 0,
    truncated: bool = False,
    agent_override: str | None = None,
) -> int | None:
    """Append one row to retrieval_router_log per cos_search/cos_doc_search/cos_task_search call."""
    if not _has_router_log(conn):
        return None
    import hashlib

    digest = hashlib.sha1((query or "").encode("utf-8")).hexdigest()[:16]
    fanout_csv = ",".join(fanout_layers) if fanout_layers else None
    try:
        cursor = conn.execute(
            "INSERT INTO retrieval_router_log "
            "(query_hash, query_shape, confidence, chosen_layer, fanout_layers, "
            " bytes_returned, truncated, agent_override) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                digest,
                _classify_query_shape(query),
                float(confidence),
                chosen_layer,
                fanout_csv,
                int(bytes_returned),
                1 if truncated else 0,
                agent_override,
            ),
        )
        conn.commit()
        return int(cursor.lastrowid) if cursor.lastrowid else None
    except sqlite3.Error as exc:
        logger.debug("retrieval_router_log insert failed: %s", exc)
        return None


def cite_retrievals(
    conn: sqlite3.Connection,
    retrieval_ids: list[int],
) -> dict:
    """Mark retrievals as actively cited by the agent."""
    if not _has_retrievals(conn):
        return {"updated": 0, "unknown": retrieval_ids}
    if not retrieval_ids:
        return {"updated": 0, "unknown": []}

    placeholders = ",".join("?" * len(retrieval_ids))
    existing = {
        r[0]
        for r in conn.execute(
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
    conn: sqlite3.Connection,
    task_id: str,
    outcome: str,
) -> int:
    """Back-fill `outcome` and `outcome_at` for all retrievals of a task."""
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
    """Adjust document_chunks.priority based on retrieval outcomes."""
    if not _has_retrievals(conn):
        return {"adjusted": 0, "gained": 0, "lost": 0, "changes": [], "status": "pre_v10_no_op"}

    rows = conn.execute(
        "SELECT source_id, was_cited, outcome "
        "FROM retrievals "
        "WHERE source_table = 'document_chunks' "
        "  AND outcome IS NOT NULL "
        "  AND created_at >= datetime('now', '-' || ? || ' days')",
        (int(lookback_days),),
    ).fetchall()

    if not rows:
        return {"adjusted": 0, "gained": 0, "lost": 0, "changes": [], "status": "no_data"}

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
        return {
            "adjusted": 0,
            "gained": 0,
            "lost": 0,
            "changes": [],
            "status": "no_effective_signal",
        }

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
        changes.append(
            {
                "chunk_id": chunk_id,
                "old": round(prev, 4),
                "new": round(new, 4),
                "delta": round(delta, 4),
            }
        )
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
