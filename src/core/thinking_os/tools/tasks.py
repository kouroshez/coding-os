"""
Coding OS — Task store query tools.

Four pure functions over the `tasks` table populated by `task_sync`:

    task_search          — semantic + structured filter (falls back to LIKE)
    task_dependencies    — upstream refs declared by a task
    task_dependents      — downstream tasks that list this one as a dependency
    task_by_filter       — structured filter only, no semantic query

All functions are read-only and graceful: when embeddings aren't available
or the tasks table is missing, they return sensible fallbacks (LIKE-based
search or empty lists) rather than raising.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from typing import Any, Optional

logger = logging.getLogger("coding_os.tools.tasks")

# Cap inputs defensively — protects against runaway queries if an agent
# passes ridiculous limits.
_MAX_LIMIT = 100

# Overfetch multiplier when semantic search is used — pulling 3x the requested
# limit gives the post-filter step room to work without losing recall.
_OVERFETCH_MULTIPLIER = 3


# ---------------------------------------------------------------------------
# task_by_filter — structured filter, no semantic
# ---------------------------------------------------------------------------


def task_by_filter(
    conn: sqlite3.Connection,
    *,
    status: str | None = None,
    domain: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """List tasks matching an optional status and/or domain filter.

    Args:
        conn: Open SQLite connection.
        status: Filter by status (open/wip/done/blocked). Optional.
        domain: Filter by domain (BACKEND/FRONTEND/DOCS/...). Optional.
        limit: Maximum results (1-100, default 20).

    Returns:
        List of task dicts sorted by task_id ascending. Empty list if the
        tasks table is missing or no matches found.
    """
    limit = max(1, min(int(limit), _MAX_LIMIT))

    sql = "SELECT task_id, title, domain, status, file_path, goal_text, dependencies FROM tasks"
    conditions: list[str] = []
    params: list[Any] = []

    if status:
        conditions.append("status = ?")
        params.append(status)
    if domain:
        conditions.append("domain = ?")
        params.append(domain)
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY task_id ASC LIMIT ?"
    params.append(limit)

    try:
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.OperationalError as exc:
        logger.debug("task_by_filter: tasks table missing: %s", exc)
        return []

    return [_row_to_dict(row) for row in rows]


# ---------------------------------------------------------------------------
# task_dependencies — upstream refs declared by the task itself
# ---------------------------------------------------------------------------


def task_dependencies(conn: sqlite3.Connection, task_id: str) -> list[dict]:
    """Return the tasks that `task_id` directly depends on (upstream).

    Reads the JSON-encoded `dependencies` column of the given task and
    joins against other rows in the tasks table to hydrate full metadata.
    Missing dependency references (e.g. a TASK-999 that was never synced)
    are silently omitted — the caller gets only real rows.

    Args:
        conn: Open SQLite connection.
        task_id: Task identifier (e.g. "TASK-199").

    Returns:
        List of dependency dicts. Empty list for unknown task or task with
        no dependencies.
    """
    from database import has_task_dependencies_table

    # v35: indexed junction lookup (PK on task_id) replaces reading + parsing
    # the JSON column. Falls back to the JSON column on a pre-v35 DB.
    if has_task_dependencies_table(conn):
        try:
            dep_rows = conn.execute(
                "SELECT t.task_id, t.title, t.domain, t.status, t.file_path, "
                "t.goal_text, t.dependencies "
                "FROM task_dependencies d JOIN tasks t ON t.task_id = d.depends_on "
                "WHERE d.task_id = ? ORDER BY t.task_id ASC",
                (task_id,),
            ).fetchall()
            return [_row_to_dict(row) for row in dep_rows]
        except sqlite3.OperationalError as exc:
            logger.debug("task_dependencies junction failed, JSON fallback: %s", exc)

    try:
        row = conn.execute(
            "SELECT dependencies FROM tasks WHERE task_id = ?", (task_id,)
        ).fetchone()
    except sqlite3.OperationalError as exc:
        logger.debug("task_dependencies: tasks table missing: %s", exc)
        return []

    if row is None or not row[0]:
        return []

    try:
        dep_ids: list[str] = json.loads(row[0])
    except (json.JSONDecodeError, TypeError):
        logger.warning("task_dependencies: malformed dependencies JSON for %s", task_id)
        return []

    if not dep_ids:
        return []

    placeholders = ",".join("?" * len(dep_ids))
    sql = (
        "SELECT task_id, title, domain, status, file_path, goal_text, dependencies "
        f"FROM tasks WHERE task_id IN ({placeholders}) "
        "ORDER BY task_id ASC"
    )
    dep_rows = conn.execute(sql, dep_ids).fetchall()
    return [_row_to_dict(row) for row in dep_rows]


# ---------------------------------------------------------------------------
# task_dependents — downstream tasks that depend on this one
# ---------------------------------------------------------------------------


def task_dependents(conn: sqlite3.Connection, task_id: str) -> list[dict]:
    """Return the tasks that declare `task_id` as a dependency (downstream).

    Implementation: scan all tasks for `"TASK-NNN"` substring inside the
    JSON-encoded `dependencies` column. The quoted form prevents false
    positives where `TASK-19` would otherwise match `TASK-195`.

    Args:
        conn: Open SQLite connection.
        task_id: Task identifier.

    Returns:
        List of dependent task dicts, sorted by task_id ascending.
    """
    from database import has_task_dependencies_table

    # v35: indexed junction lookup (idx on depends_on) replaces the O(n)
    # `dependencies LIKE '%"TASK-NNN"%'` full-table scan. Falls back to the
    # LIKE scan on a pre-v35 DB.
    if has_task_dependencies_table(conn):
        try:
            rows = conn.execute(
                "SELECT t.task_id, t.title, t.domain, t.status, t.file_path, "
                "t.goal_text, t.dependencies "
                "FROM task_dependencies d JOIN tasks t ON t.task_id = d.task_id "
                "WHERE d.depends_on = ? ORDER BY t.task_id ASC",
                (task_id,),
            ).fetchall()
            return [_row_to_dict(row) for row in rows]
        except sqlite3.OperationalError as exc:
            logger.debug("task_dependents junction failed, LIKE fallback: %s", exc)

    # Build the JSON-quoted search pattern. dependencies is stored as
    # json.dumps([...]) so individual task IDs appear as "TASK-NNN"
    # (with quotes). Searching for the quoted form eliminates substring
    # false positives like TASK-19 matching TASK-195.
    quoted_needle = f'"{task_id}"'
    sql = (
        "SELECT task_id, title, domain, status, file_path, goal_text, dependencies "
        "FROM tasks WHERE dependencies LIKE ? ORDER BY task_id ASC"
    )
    try:
        rows = conn.execute(sql, (f"%{quoted_needle}%",)).fetchall()
    except sqlite3.OperationalError as exc:
        logger.debug("task_dependents: tasks table missing: %s", exc)
        return []

    return [_row_to_dict(row) for row in rows]


# ---------------------------------------------------------------------------
# task_search — semantic + structured filter (with LIKE fallback)
# ---------------------------------------------------------------------------


def task_search(
    conn: sqlite3.Connection,
    query: str,
    *,
    status: str | None = None,
    domain: str | None = None,
    limit: int = 10,
    threshold: float = 0.1,
) -> list[dict]:
    """Semantic task search with optional status/domain filters.

    Tries semantic search first (via the embeddings pipeline).
    If embeddings are unavailable, the tasks table has no embeddings, or
    zero results cross the threshold, falls back to LIKE on title + goal.

    Args:
        conn: Open SQLite connection.
        query: Natural language query (e.g. "payment splitting").
        status: Optional status filter (open/wip/done/blocked).
        domain: Optional domain filter (BACKEND/FRONTEND/DOCS/...).
        limit: Maximum results (1-100, default 10).
        threshold: Minimum cosine similarity for semantic hits (default 0.1).

    Returns:
        List of task dicts with `score` field, sorted by score descending
        for semantic hits or by created_at descending for LIKE fallback.
    """
    if not query or not query.strip():
        return []

    limit = max(1, min(int(limit), _MAX_LIMIT))

    semantic_hits = _try_semantic_search(conn, query, limit * _OVERFETCH_MULTIPLIER, threshold)

    if semantic_hits:
        return _hydrate_and_filter(conn, semantic_hits, status, domain, limit)

    # Fallback: LIKE on title + goal_text
    return _like_fallback(conn, query, status, domain, limit)


def _try_semantic_search(
    conn: sqlite3.Connection,
    query: str,
    limit: int,
    threshold: float,
) -> list[dict]:
    """Run an embedding similarity search scoped to source_table='tasks'.

    Returns an empty list on any failure (module missing, table missing,
    model load error) so the caller can fall back to LIKE.
    """
    try:
        from embeddings import is_available, search_similar
    except ImportError as exc:
        logger.debug("task_search semantic unavailable (module): %s", exc)
        return []

    if not is_available():
        return []

    try:
        return search_similar(
            conn,
            query=query,
            source_tables=["tasks"],
            limit=limit,
            threshold=threshold,
        )
    except sqlite3.OperationalError as exc:
        logger.debug("task_search semantic skipped (table missing): %s", exc)
        return []
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("task_search semantic skipped (unexpected): %s", exc)
        return []


def _hydrate_and_filter(
    conn: sqlite3.Connection,
    semantic_hits: list[dict],
    status: str | None,
    domain: str | None,
    limit: int,
) -> list[dict]:
    """Hydrate semantic hit rowids into full task dicts and apply filters.

    Semantic hits reference tasks by rowid (the integer hidden OID), not
    task_id, because embeddings.source_id is integer-typed. We join back
    through rowid to get the real row.
    """
    if not semantic_hits:
        return []

    rowids = [h["source_id"] for h in semantic_hits]
    score_by_rowid = {h["source_id"]: h["score"] for h in semantic_hits}

    placeholders = ",".join("?" * len(rowids))
    sql = (
        "SELECT rowid, task_id, title, domain, status, file_path, goal_text, "
        f"dependencies FROM tasks WHERE rowid IN ({placeholders})"
    )
    try:
        rows = conn.execute(sql, rowids).fetchall()
    except sqlite3.OperationalError as exc:
        logger.debug("task_search hydrate failed: %s", exc)
        return []

    hydrated: list[dict] = []
    for row in rows:
        row_status = row["status"]
        row_domain = row["domain"]
        if status is not None and row_status != status:
            continue
        if domain is not None and row_domain != domain:
            continue

        result = _row_to_dict(row)
        result["score"] = score_by_rowid.get(row["rowid"], 0.0)
        hydrated.append(result)

    hydrated.sort(key=lambda d: d["score"], reverse=True)
    return hydrated[:limit]


def _fts_fallback(
    conn: sqlite3.Connection,
    query: str,
    status: str | None,
    domain: str | None,
    limit: int,
) -> list[dict]:
    """FTS5 MATCH over tasks_fts(title, goal_text), joined back to tasks."""
    sql = (
        "SELECT t.task_id, t.title, t.domain, t.status, t.file_path, "
        "t.goal_text, t.dependencies "
        "FROM tasks_fts f JOIN tasks t ON t.rowid = f.rowid "
        "WHERE tasks_fts MATCH ?"
    )
    params: list[Any] = [query]
    if status:
        sql += " AND t.status = ?"
        params.append(status)
    if domain:
        sql += " AND t.domain = ?"
        params.append(domain)
    sql += " ORDER BY f.rank LIMIT ?"
    params.append(limit)

    rows = conn.execute(sql, params).fetchall()
    results = []
    for row in rows:
        result = _row_to_dict(row)
        result["score"] = 0.6
        results.append(result)
    return results


def _like_fallback(
    conn: sqlite3.Connection,
    query: str,
    status: str | None,
    domain: str | None,
    limit: int,
) -> list[dict]:
    """Lexical fallback when embeddings aren't available.

    Uses the FTS5 tasks_fts index (v35) when present; degrades to a LIKE
    scan only when FTS5 is unavailable or the query trips FTS5 MATCH syntax.
    """
    from database import has_tasks_fts

    if has_tasks_fts(conn):
        try:
            return _fts_fallback(conn, query, status, domain, limit)
        except sqlite3.OperationalError as exc:
            logger.debug("task_search FTS failed, LIKE fallback: %s", exc)

    like_pattern = f"%{query}%"
    sql = (
        "SELECT task_id, title, domain, status, file_path, goal_text, dependencies "
        "FROM tasks WHERE (title LIKE ? OR goal_text LIKE ?)"
    )
    params: list[Any] = [like_pattern, like_pattern]

    if status:
        sql += " AND status = ?"
        params.append(status)
    if domain:
        sql += " AND domain = ?"
        params.append(domain)
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    try:
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.OperationalError as exc:
        logger.debug("task_search LIKE fallback failed: %s", exc)
        return []

    results = []
    for row in rows:
        result = _row_to_dict(row)
        # LIKE hits have a fixed moderate score so callers can still sort
        result["score"] = 0.5
        results.append(result)
    return results


# ---------------------------------------------------------------------------
# Row shaping helper
# ---------------------------------------------------------------------------


def _row_to_dict(row) -> dict:
    """Convert a sqlite3.Row into the canonical task dict shape.

    Dependencies are eagerly JSON-parsed so callers see a real list.
    """
    raw_deps = row["dependencies"]
    try:
        deps = json.loads(raw_deps) if raw_deps else []
    except (json.JSONDecodeError, TypeError):
        deps = []

    return {
        "task_id": row["task_id"],
        "title": row["title"],
        "domain": row["domain"],
        "status": row["status"],
        "file_path": row["file_path"],
        "goal_text": row["goal_text"],
        "dependencies": deps,
    }
