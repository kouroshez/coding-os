"""board_os workflow — task dependency resolution and cycle detection.

Junction-table (v35+) queries with a JSON-column fallback, plus the R-L-29
cycle check that guards a proposed depends_on edge set.
"""

from __future__ import annotations

import json
import logging
import sqlite3

logger = logging.getLogger("coding_os.board_os.workflow")


def _has_task_dependencies_table(conn: sqlite3.Connection) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='task_dependencies'"
        ).fetchone()
        is not None
    )


def incomplete_dependencies(conn: sqlite3.Connection, task_id: str) -> list[str]:
    """Return the depends_on ids of `task_id` whose status is not 'complete'.

    Reuses the same junction-then-JSON-column resolution as
    tools.tasks.task_dependencies: on a v35+ DB it joins the indexed
    task_dependencies junction; otherwise it reads the JSON `dependencies`
    column. A dep id that has no matching tasks row (never synced) counts as
    incomplete so a dangling prerequisite can't silently unblock a pull.
    """
    if _has_task_dependencies_table(conn):
        try:
            rows = conn.execute(
                "SELECT d.depends_on, t.status "
                "FROM task_dependencies d "
                "LEFT JOIN tasks t ON t.task_id = d.depends_on "
                "WHERE d.task_id = ? ORDER BY d.depends_on ASC",
                (task_id,),
            ).fetchall()
            return [str(dep) for dep, status in rows if status != "complete"]
        except sqlite3.OperationalError as exc:
            logger.debug("incomplete_dependencies junction failed, JSON fallback: %s", exc)

    row = conn.execute("SELECT dependencies FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
    if row is None or not row[0]:
        return []
    try:
        dep_ids = [str(d) for d in json.loads(row[0])]
    except (json.JSONDecodeError, TypeError):
        return []
    if not dep_ids:
        return []
    placeholders = ",".join("?" * len(dep_ids))
    status_by_dep = {
        str(r[0]): str(r[1])
        for r in conn.execute(
            f"SELECT task_id, status FROM tasks WHERE task_id IN ({placeholders})",
            dep_ids,
        ).fetchall()
    }
    return [dep for dep in dep_ids if status_by_dep.get(dep) != "complete"]


def dependents_of(conn: sqlite3.Connection, task_id: str) -> list[str]:
    """Return the ids of tasks that declare `task_id` in their depends_on.

    The reverse of incomplete_dependencies. Drives the completion cascade:
    when a prerequisite completes, its dependents are the only candidates that
    could newly become runnable. Uses the indexed task_dependencies(depends_on)
    junction on a v35+ DB; otherwise scans the JSON `dependencies` column.
    """
    if _has_task_dependencies_table(conn):
        try:
            rows = conn.execute(
                "SELECT task_id FROM task_dependencies WHERE depends_on = ? ORDER BY task_id ASC",
                (task_id,),
            ).fetchall()
            return [str(r[0]) for r in rows]
        except sqlite3.OperationalError as exc:
            logger.debug("dependents_of junction failed, JSON fallback: %s", exc)

    rows = conn.execute(
        "SELECT task_id, dependencies FROM tasks "
        "WHERE dependencies IS NOT NULL AND dependencies != ''"
    ).fetchall()
    found: list[str] = []
    for dependent_id, deps_raw in rows:
        try:
            deps = [str(d) for d in json.loads(deps_raw)]
        except (json.JSONDecodeError, TypeError):
            continue
        if task_id in deps:
            found.append(str(dependent_id))
    return sorted(found)


def validate_dependencies_no_cycle(
    conn: sqlite3.Connection, task_id: str, new_deps: list[str]
) -> list[str]:
    """Detect cycles a proposed task_id -> new_deps edge set would create. R-L-29.

    On a v35 DB this runs a targeted recursive CTE over the task_dependencies
    junction — for each proposed dep it asks whether that dep can already reach
    task_id, traversing only the reachable subgraph instead of loading every
    task row (TASK-229). Falls back to the full-scan DFS on a pre-v35 DB.
    Returns a list of cycle paths (empty if no cycle).
    """
    if not new_deps:
        return []
    if not _has_task_dependencies_table(conn):
        return _validate_dependencies_no_cycle_fallback(conn, task_id, new_deps)

    cycles: list[str] = []
    if task_id in new_deps:
        cycles.append(f"{task_id} → {task_id}")  # trivial self-cycle
    for dep in new_deps:
        if dep == task_id:
            continue
        # Can `dep` already reach task_id (excluding task_id's own edges, which
        # this edit replaces)? If so, task_id -> dep closes a cycle. depth guard
        # terminates on any pre-existing cycle in the data.
        # UNION (not UNION ALL) dedups on tid, so a dense DAG with many distinct
        # paths to the same node is bounded to O(reachable nodes) instead of
        # enumerating every path — and the dedup makes any pre-existing data
        # cycle terminate without needing a depth guard.
        row = conn.execute(
            """
            WITH RECURSIVE reachable(tid) AS (
                SELECT ?
                UNION
                SELECT td.depends_on
                FROM task_dependencies td
                JOIN reachable r ON td.task_id = r.tid
                WHERE td.task_id != ?
            )
            SELECT 1 FROM reachable WHERE tid = ? LIMIT 1
            """,
            (dep, task_id, task_id),
        ).fetchone()
        if row:
            cycles.append(f"{task_id} → {dep} → … → {task_id}")
    return cycles


def _validate_dependencies_no_cycle_fallback(
    conn: sqlite3.Connection, task_id: str, new_deps: list[str]
) -> list[str]:
    """Pre-v35 fallback: DFS over the full dependency graph (loads all rows)."""
    deps_by_task: dict[str, list[str]] = {}
    for row in conn.execute("SELECT task_id, dependencies FROM tasks"):
        if row[0] == task_id:
            continue
        raw = row[1] or ""
        # Dependencies may be stored as JSON (new style) or as a
        # newline/comma-separated string (legacy). Handle both.
        parsed_deps: list[str] = []
        if isinstance(raw, str) and raw.strip():
            text = raw.strip()
            if text.startswith("["):
                try:
                    parsed_deps = [str(d) for d in json.loads(text)]
                except json.JSONDecodeError:
                    parsed_deps = []
            else:
                import re as _re

                parsed_deps = _re.findall(r"TASK-(?:[A-Z][A-Z0-9]*-)?\d+", text)
        deps_by_task[row[0]] = parsed_deps
    deps_by_task[task_id] = list(new_deps)

    cycles: list[str] = []
    visited: set[str] = set()
    stack: list[str] = []

    def dfs(node: str) -> None:
        if node in stack:
            cycle = [*stack[stack.index(node) :], node]
            cycles.append(" → ".join(cycle))
            return
        if node in visited:
            return
        visited.add(node)
        stack.append(node)
        for dep in deps_by_task.get(node, []):
            dfs(dep)
        stack.pop()

    dfs(task_id)
    return cycles
