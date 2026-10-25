"""
Coding OS — retrieval audit log.

`cos_doc_search` and `cos_task_search` call `log_retrieval` after producing
results (each row lands in `retrievals`, and its id comes back to the caller as
`retrieval_ids`), and `log_router_decision` records which ranking path answered.
Both are read-tolerant: missing tables return cleanly instead of raising.
"""

from __future__ import annotations

import contextlib
import logging
import sqlite3
from collections.abc import Iterable

logger = logging.getLogger("coding_os.tools.retrieve")


def _has_retrievals(conn: sqlite3.Connection) -> bool:
    try:
        conn.execute("SELECT 1 FROM retrievals LIMIT 1")
        return True
    except sqlite3.OperationalError:
        return False


def _read_session_id() -> str:
    """Return the active session id (or 'ses-unknown'). Mirrors the resolution
    order in core/hooks/cos-env.sh
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
    # Priority 3 — legacy flat layout (kept for first-run migration only)
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
    with contextlib.suppress(sqlite3.OperationalError):
        conn.commit()
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
    """Append one row to retrieval_router_log per cos_doc_search/cos_task_search call."""
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
