"""
Coding OS — Task store sync (Phase C.3).

Walks `docs/tasks/*.md`, parses each file via `task_parser`, reads status
from `docs/tasks.md`, and upserts into the `tasks` table. Embeds the
result via the existing Phase B `embeddings` pipeline (fire-and-forget,
graceful degradation when sentence-transformers is unavailable).

Files remain SSOT — this module never writes markdown. If the DB is
deleted or the tasks table is dropped, `sync_tasks(..., force=True)`
rebuilds it from scratch.

Public API:
    sync_tasks(conn, project_root, tasks_dir=None, index_file=None, force=False) -> dict
    sync_status_only(conn, project_root, index_file=None) -> dict
    parse_task_index(index_path) -> dict[task_id, status]

CLI entry point:
    python -m task_sync [--project-root PATH] [--db PATH] [--force]
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sqlite3
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger("coding_os.task_sync")

# Status marker patterns (order matters — blocked must come before open)
_STATUS_BLOCKED_RE = re.compile(
    r"^\-\s*\(BLOCKED:[^)]*\)\s*(TASK-\d+):", re.MULTILINE
)
_STATUS_DONE_RE = re.compile(r"^\-\s*\[x\]\s*(TASK-\d+):", re.MULTILINE)
_STATUS_WIP_RE = re.compile(r"^\-\s*\[/\]\s*(TASK-\d+):", re.MULTILINE)
_STATUS_OPEN_RE = re.compile(r"^\-\s*\[\s\]\s*(TASK-\d+):", re.MULTILINE)


def parse_task_index(index_path: Path) -> dict[str, str]:
    """Parse `docs/tasks.md` into a {task_id: status} map.

    Recognizes the four canonical status markers documented in
    `docs/governance/task-lifecycle.md`:
        `- [ ]` → 'open'
        `- [/]` → 'wip'
        `- [x]` → 'done'
        `- (BLOCKED: reason)` → 'blocked'

    Task numbers in the index are canonicalized to zero-padded three-digit
    format (`TASK-003` rather than `TASK-3`) to match `task_parser`.

    Args:
        index_path: Path to `docs/tasks.md`.

    Returns:
        Dictionary mapping canonical task_id → status. Empty dict if the
        file is missing.
    """
    if not index_path.exists():
        return {}

    content = index_path.read_text(encoding="utf-8")
    statuses: dict[str, str] = {}

    # Order matters: blocked and wip before done/open so later matchers
    # don't overwrite earlier ones (they shouldn't, but defensive).
    for regex, status in (
        (_STATUS_BLOCKED_RE, "blocked"),
        (_STATUS_DONE_RE, "done"),
        (_STATUS_WIP_RE, "wip"),
        (_STATUS_OPEN_RE, "open"),
    ):
        for match in regex.finditer(content):
            raw_id = match.group(1)
            canonical = _canonicalize_task_id(raw_id)
            statuses[canonical] = status

    return statuses


def _canonicalize_task_id(raw: str) -> str:
    """Convert 'TASK-3' → 'TASK-003' (zero-padded to 3 digits)."""
    match = re.match(r"TASK-(\d+)", raw)
    if not match:
        return raw
    return f"TASK-{int(match.group(1)):03d}"


def sync_tasks(
    conn: sqlite3.Connection,
    *,
    project_root: Path,
    tasks_dir: Optional[Path] = None,
    index_file: Optional[Path] = None,
    force: bool = False,
) -> dict:
    """Sync `docs/tasks/*.md` files into the `tasks` table.

    Mtime-aware incremental sync — only files whose mtime changed since
    the last sync are re-parsed, matching the pattern used by doc_indexer.

    Args:
        conn: Open migrated SQLite connection (must include migration v6).
        project_root: Project root used for storing relative file paths.
        tasks_dir: Directory containing TASK-###-slug.md files.
            Defaults to `project_root / "docs/tasks"`.
        index_file: Path to the task index. Defaults to
            `project_root / "docs/tasks.md"`.
        force: When True, re-sync every file regardless of mtime.

    Returns:
        Stats dict with keys: processed, skipped, new, updated, deleted,
        errors.
    """
    # Resolve paths consistently to avoid the /tmp vs /private/tmp mismatch
    # that bit doc_indexer earlier.
    project_root_resolved = project_root.resolve()
    tasks_dir = (tasks_dir or project_root_resolved / "docs" / "tasks").resolve()
    index_file = (index_file or project_root_resolved / "docs" / "tasks.md").resolve()

    stats = {
        "processed": 0,
        "skipped": 0,
        "new": 0,
        "updated": 0,
        "deleted": 0,
        "errors": 0,
    }

    if not tasks_dir.exists():
        logger.debug("sync_tasks: tasks_dir missing, nothing to sync: %s", tasks_dir)
        return stats

    status_by_id = parse_task_index(index_file)
    seen_task_ids: set[str] = set()

    # Defer parser import until needed so a bare `task_sync` import works
    # even when the parser file has been moved (shouldn't happen but keeps
    # the module loosely coupled).
    from task_parser import parse_task_file

    for file_path in sorted(tasks_dir.rglob("*.md")):
        # Skip archive subdirectories — past tasks that shouldn't re-enter
        # the active index.
        if "archive" in file_path.parts:
            continue

        stats["processed"] += 1
        rel_path = str(file_path.resolve().relative_to(project_root_resolved))

        try:
            file_mtime = int(file_path.stat().st_mtime)
        except OSError as exc:
            logger.warning("sync_tasks: cannot stat %s: %s", rel_path, exc)
            stats["errors"] += 1
            continue

        if not force:
            existing = conn.execute(
                "SELECT task_id, mtime FROM tasks WHERE file_path = ?",
                (rel_path,),
            ).fetchone()
            if existing is not None and existing[1] >= file_mtime:
                seen_task_ids.add(existing[0])
                # Status may have changed in tasks.md even though the detail
                # file didn't — patch it in-place without a full re-parse.
                new_status = status_by_id.get(existing[0])
                if new_status:
                    conn.execute(
                        "UPDATE tasks SET status = ?, updated_at = CURRENT_TIMESTAMP "
                        "WHERE task_id = ? AND status != ?",
                        (new_status, existing[0], new_status),
                    )
                stats["skipped"] += 1
                continue

        try:
            content = file_path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("sync_tasks: cannot read %s: %s", rel_path, exc)
            stats["errors"] += 1
            continue

        parsed = parse_task_file(content)
        if parsed is None:
            logger.debug("sync_tasks: %s is not a task file, skipping", rel_path)
            stats["errors"] += 1
            continue

        status = status_by_id.get(parsed.task_id, "open")
        action = _upsert_task(conn, parsed, rel_path, file_mtime, status)
        if action == "inserted":
            stats["new"] += 1
        elif action == "updated":
            stats["updated"] += 1

        seen_task_ids.add(parsed.task_id)
        _embed_task_safe(conn, parsed)

    # Orphan cleanup — any row whose task_id wasn't seen this pass is a file
    # that was deleted / renamed out of the active set.
    stats["deleted"] = _delete_orphans(conn, seen_task_ids)

    conn.commit()
    return stats


def sync_status_only(
    conn: sqlite3.Connection,
    *,
    project_root: Path,
    index_file: Optional[Path] = None,
) -> dict:
    """Fast path — update only the `status` column from `docs/tasks.md`.

    Called by `make task-done` / `task-start` when only the status changed
    and a full re-parse + re-embed would be overkill.

    Returns:
        Stats dict: {updated: int, unchanged: int}.
    """
    project_root_resolved = project_root.resolve()
    index_file = (index_file or project_root_resolved / "docs" / "tasks.md").resolve()

    stats = {"updated": 0, "unchanged": 0}
    status_by_id = parse_task_index(index_file)
    if not status_by_id:
        return stats

    for task_id, new_status in status_by_id.items():
        cursor = conn.execute(
            "UPDATE tasks SET status = ?, updated_at = CURRENT_TIMESTAMP "
            "WHERE task_id = ? AND status != ?",
            (new_status, task_id, new_status),
        )
        if cursor.rowcount > 0:
            stats["updated"] += 1
        else:
            stats["unchanged"] += 1
    conn.commit()
    return stats


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _upsert_task(
    conn: sqlite3.Connection,
    parsed,
    rel_path: str,
    mtime: int,
    status: str,
) -> str:
    """Insert or replace a row in the `tasks` table.

    Returns:
        'inserted' if a new row was created, 'updated' if an existing row
        was replaced.
    """
    existing = conn.execute(
        "SELECT task_id FROM tasks WHERE task_id = ?", (parsed.task_id,)
    ).fetchone()

    payload = (
        parsed.task_id,
        parsed.title,
        parsed.domain,
        status,
        rel_path,
        parsed.content_hash,
        mtime,
        parsed.goal_text,
        json.dumps(parsed.scope_in),
        json.dumps(parsed.scope_out),
        json.dumps(parsed.requirements),
        json.dumps(parsed.dependencies),
        json.dumps(parsed.source_of_truth),
        json.dumps(parsed.read_first),
        parsed.open_questions,
        parsed.rabbit_holes,
        parsed.verification,
    )

    if existing:
        conn.execute(
            "UPDATE tasks SET title = ?, domain = ?, status = ?, file_path = ?, "
            "content_hash = ?, mtime = ?, goal_text = ?, scope_in = ?, scope_out = ?, "
            "requirements = ?, dependencies = ?, source_of_truth = ?, read_first = ?, "
            "open_questions = ?, rabbit_holes = ?, verification = ?, "
            "updated_at = CURRENT_TIMESTAMP WHERE task_id = ?",
            payload[1:] + (parsed.task_id,),
        )
        return "updated"

    conn.execute(
        "INSERT INTO tasks "
        "(task_id, title, domain, status, file_path, content_hash, mtime, "
        "goal_text, scope_in, scope_out, requirements, dependencies, "
        "source_of_truth, read_first, open_questions, rabbit_holes, verification) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        payload,
    )
    return "inserted"


def _delete_orphans(conn: sqlite3.Connection, seen_task_ids: set[str]) -> int:
    """Delete rows whose task_id isn't in the current seen set.

    Also removes the corresponding embeddings rows so the index doesn't
    carry stale vectors for deleted tasks.

    Returns:
        Count of deleted task rows.
    """
    existing_ids = {
        row[0]
        for row in conn.execute("SELECT task_id FROM tasks").fetchall()
    }
    orphans = existing_ids - seen_task_ids
    if not orphans:
        return 0

    # Need the row IDs for embeddings cleanup (embeddings.source_id is integer,
    # but tasks uses task_id string as PK — we use rowid for the linkage).
    for task_id in orphans:
        # Look up numeric rowid (tasks.rowid == hidden OID in SQLite)
        row = conn.execute(
            "SELECT rowid FROM tasks WHERE task_id = ?", (task_id,)
        ).fetchone()
        if row is None:
            continue
        rowid = row[0]
        conn.execute(
            "DELETE FROM embeddings WHERE source_table = 'tasks' AND source_id = ?",
            (rowid,),
        )
        conn.execute("DELETE FROM tasks WHERE task_id = ?", (task_id,))

    return len(orphans)


def _embed_task_safe(conn: sqlite3.Connection, parsed) -> None:
    """Embed title + goal + requirements for a parsed task.

    Fire-and-forget: if the embeddings module is missing, the rag extras
    are not installed, or the embeddings table doesn't exist (pre-v5 DB),
    we log at debug and continue silently. Never crashes the sync.
    """
    try:
        from embeddings import upsert_embedding
    except ImportError as exc:
        logger.debug("task embedding skipped (module unavailable): %s", exc)
        return

    # Use the tasks rowid as the foreign key so embeddings.source_id stays
    # integer-typed across source tables.
    row = conn.execute(
        "SELECT rowid FROM tasks WHERE task_id = ?", (parsed.task_id,)
    ).fetchone()
    if row is None:
        return

    # Embed the most actionable compact signal: title + goal + requirements.
    # Scope/rabbit-holes/verification are noisy for retrieval.
    text_to_embed = " ".join(
        filter(
            None,
            [
                parsed.title,
                parsed.goal_text,
                " ".join(parsed.requirements),
            ],
        )
    )
    if not text_to_embed.strip():
        return

    try:
        upsert_embedding(conn, "tasks", row[0], text_to_embed)
    except sqlite3.OperationalError as exc:
        logger.debug("task embedding skipped (table missing): %s", exc)
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("task embedding skipped (unexpected): %s", exc)


# ---------------------------------------------------------------------------
# CLI entry point — `python -m task_sync`
# ---------------------------------------------------------------------------

def _main() -> None:
    parser = argparse.ArgumentParser(description="Sync docs/tasks/ → thinking_os.db")
    parser.add_argument(
        "--project-root",
        type=str,
        default=".",
        help="Project root (default: current directory)",
    )
    parser.add_argument(
        "--db",
        type=str,
        default=None,
        help="Override DB path (defaults to COS_DB_PATH)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-sync every file regardless of mtime",
    )
    args = parser.parse_args()

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from db import init_db

    conn = init_db(args.db)
    try:
        stats = sync_tasks(conn, project_root=Path(args.project_root), force=args.force)
    finally:
        conn.close()
    print(json.dumps({"status": "ok", "stats": stats}, indent=2))


if __name__ == "__main__":
    _main()
