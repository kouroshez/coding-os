"""board-os sync — Phase L mtime-incremental task→DB sync (L.1).

Walks `docs/tasks/*.md`, parses each via `parser.parse_task`, and upserts
into the `tasks` table (migration v13 columns) plus appends to
`task_status_history` on status changes.

Parallel to `core/thinking-os/task_sync.py` (Phase C) but writes the
extended v13 schema.  The Phase C sync is NOT removed — this module
can coexist because both write to the same `tasks` table using
idempotent INSERT OR REPLACE semantics on task_id.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from pathlib import Path

from core.board_os.parser import ParsedTask, parse_task

logger = logging.getLogger("coding_os.board_os.sync")


_TASK_FILENAME_RE = "docs/tasks/TASK-*.md"


def _iter_task_files(project_root: Path) -> list[Path]:
    tasks_dir = (project_root / "docs" / "tasks").resolve()
    if not tasks_dir.exists():
        return []
    files: list[Path] = []
    for p in tasks_dir.glob("TASK-*.md"):
        if p.is_file():
            files.append(p.resolve())
    return sorted(files)


def _fetch_existing(
    conn: sqlite3.Connection, task_id: str
) -> dict[str, object] | None:
    row = conn.execute(
        "SELECT task_id, status, mtime, content_hash "
        "FROM tasks WHERE task_id = ?",
        (task_id,),
    ).fetchone()
    if row is None:
        return None
    return {
        "task_id": row[0],
        "status": row[1],
        "mtime": row[2],
        "content_hash": row[3],
    }


def _upsert_task(
    conn: sqlite3.Connection,
    parsed: ParsedTask,
    *,
    file_path: str,
    mtime: int,
    content_hash: str,
) -> None:
    labels_json = json.dumps(list(parsed.labels))
    now = int(time.time())
    conn.execute(
        """
        INSERT INTO tasks (
            task_id, title, domain, status, file_path, content_hash, mtime,
            swimlane, kind, epic, labels_json, priority, appetite,
            started_at, completed_at, agent_session
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(task_id) DO UPDATE SET
            title           = excluded.title,
            domain          = excluded.domain,
            status          = excluded.status,
            file_path       = excluded.file_path,
            content_hash    = excluded.content_hash,
            mtime           = excluded.mtime,
            swimlane        = excluded.swimlane,
            kind            = excluded.kind,
            epic            = excluded.epic,
            labels_json     = excluded.labels_json,
            priority        = excluded.priority,
            appetite        = excluded.appetite,
            started_at      = COALESCE(excluded.started_at, tasks.started_at),
            completed_at    = COALESCE(excluded.completed_at, tasks.completed_at),
            agent_session   = excluded.agent_session,
            updated_at      = CURRENT_TIMESTAMP
        """,
        (
            parsed.task_id,
            parsed.title,
            parsed.swimlane or None,
            parsed.status,
            file_path,
            content_hash,
            mtime,
            parsed.swimlane or None,
            parsed.kind or None,
            parsed.epic,
            labels_json,
            parsed.priority,
            parsed.appetite,
            _iso_to_epoch(parsed.started),
            _iso_to_epoch(parsed.completed),
            parsed.agent_session,
        ),
    )

    # Update work_log_last_5 from parsed lines (newest-first per convention
    # in MD file, which appends at bottom so "last 5" is tail).
    last_5 = list(parsed.work_log_lines[-5:])
    conn.execute(
        "UPDATE tasks SET work_log_last_5 = ? WHERE task_id = ?",
        (json.dumps(last_5), parsed.task_id),
    )


def _record_status_change(
    conn: sqlite3.Connection,
    task_id: str,
    old_status: str,
    new_status: str,
    agent_session: str | None,
    reason: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO task_status_history
            (task_id, old_status, new_status, agent_session, reason, transitioned_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (task_id, old_status, new_status, agent_session, reason, int(time.time())),
    )


def _iso_to_epoch(iso: str | None) -> int | None:
    if not iso:
        return None
    try:
        from datetime import datetime, timezone
        return int(datetime.fromisoformat(iso).replace(tzinfo=timezone.utc).timestamp())
    except Exception:
        return None


def sync_one(
    conn: sqlite3.Connection,
    file_path: Path,
    *,
    project_root: Path | None = None,
) -> ParsedTask | None:
    """Sync a single file.  Called by auto-task-sync hook on Write/Edit."""
    content = file_path.read_text(encoding="utf-8")
    parsed = parse_task(content, path=file_path)
    if parsed is None:
        logger.debug("unparseable: %s", file_path)
        return None

    project_root = project_root or Path.cwd()
    try:
        rel_path = str(file_path.resolve().relative_to(project_root.resolve()))
    except ValueError:
        rel_path = str(file_path)

    mtime = int(file_path.stat().st_mtime)
    content_hash = parsed.body_hash

    existing = _fetch_existing(conn, parsed.task_id)
    old_status = existing["status"] if existing else None

    _upsert_task(
        conn, parsed, file_path=rel_path, mtime=mtime, content_hash=content_hash,
    )

    if old_status and old_status != parsed.status:
        _record_status_change(
            conn,
            parsed.task_id,
            str(old_status),
            parsed.status,
            parsed.agent_session,
        )

    conn.commit()
    return parsed


def sync_all(
    conn: sqlite3.Connection, project_root: Path | None = None
) -> dict[str, int]:
    """Full sync of docs/tasks/.  Returns counters for observability."""
    project_root = (project_root or Path.cwd()).resolve()
    files = _iter_task_files(project_root)

    stats = {"scanned": 0, "upserted": 0, "skipped_unchanged": 0, "parse_errors": 0}

    for path in files:
        stats["scanned"] += 1
        mtime = int(path.stat().st_mtime)
        row = conn.execute(
            "SELECT mtime FROM tasks WHERE file_path = ?",
            (str(path.relative_to(project_root)),),
        ).fetchone()
        if row and row[0] == mtime:
            stats["skipped_unchanged"] += 1
            continue
        result = sync_one(conn, path, project_root=project_root)
        if result is None:
            stats["parse_errors"] += 1
        else:
            stats["upserted"] += 1

    return stats
