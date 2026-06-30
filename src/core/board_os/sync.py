"""board_os sync — mtime-incremental task→DB sync.

Walks `docs/tasks/*.md`, parses each via `parser.parse_task`, and upserts
into the `tasks` table plus appends to `task_status_history` on status
changes.

This is the SOLE tasks-table writer since the legacy v6 sync was retired
(TASK-398) — `core/thinking_os/task_sync.py` is a compatibility shim that
delegates here. Files remain SSOT; the table is a derived cache.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

from board_os.parser import ParsedTask, detect_duplicate_frontmatter, parse_task

logger = logging.getLogger("coding_os.board_os.sync")


_TASK_FILENAME_RE = "docs/tasks/TASK-*.md"

# Forward order of the pipeline states. A file-sync that moves a task to a
# LOWER rank without going through the workflow is the signature of a stale
# revert (e.g. `git checkout` restoring an old card) and must be surfaced.
_STATUS_RANK = {"icebox": 0, "ready": 1, "in_progress": 2, "testing": 3, "complete": 4}

_SYNC_CONFLICT_REASON = "sync-conflict: file moved task backward (possible stale revert)"


def _iter_task_files(project_root: Path) -> list[Path]:
    tasks_dir = (project_root / "docs" / "tasks").resolve()
    if not tasks_dir.exists():
        return []
    files: list[Path] = []
    for p in tasks_dir.glob("TASK-*.md"):
        if p.is_file():
            files.append(p.resolve())
    return sorted(files)


def _fetch_existing(conn: sqlite3.Connection, task_id: str) -> dict[str, object] | None:
    row = conn.execute(
        "SELECT task_id, status, mtime, content_hash FROM tasks WHERE task_id = ?",
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
    mtime: float,
    content_hash: str,
) -> None:
    labels_json = json.dumps(list(parsed.labels))
    deps_json = json.dumps(list(parsed.depends_on))
    blocked_by_json = json.dumps(list(parsed.blocked_by))
    references_json = json.dumps(list(parsed.references))
    created_at = parsed.created or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        """
        INSERT INTO tasks (
            task_id, title, domain, status, file_path, content_hash, mtime,
            swimlane, kind, epic, labels_json, priority, appetite,
            started_at, completed_at, agent_session, dependencies,
            goal_text, blocked_by_json, references_json, external_ref, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            dependencies    = excluded.dependencies,
            goal_text       = excluded.goal_text,
            blocked_by_json = excluded.blocked_by_json,
            references_json = excluded.references_json,
            external_ref    = excluded.external_ref,
            created_at      = COALESCE(tasks.created_at, excluded.created_at),
            updated_at      = CURRENT_TIMESTAMP
        """,
        (
            parsed.task_id,
            parsed.title,
            # Legacy `domain` column convention is UPPERCASE (BACKEND/DOCS/…);
            # the cos_task_* tools filter on it case-sensitively.
            (parsed.swimlane or "").upper() or None,
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
            deps_json,
            parsed.outcome,
            blocked_by_json,
            references_json,
            parsed.external_ref,
            created_at,
        ),
    )

    # Update work_log_last_5 from parsed lines (newest-first per convention
    # in MD file, which appends at bottom so "last 5" is tail).
    last_5 = list(parsed.work_log_lines[-5:])
    conn.execute(
        "UPDATE tasks SET work_log_last_5 = ? WHERE task_id = ?",
        (json.dumps(last_5), parsed.task_id),
    )
    # The task_dependencies junction (v35) is maintained by DB triggers off
    # the dependencies column written above — no per-writer code needed.


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
        return int(datetime.fromisoformat(iso).replace(tzinfo=timezone.utc).timestamp())
    except Exception:
        return None


def _is_backward(old_status: str, new_status: str) -> bool:
    old_rank = _STATUS_RANK.get(old_status)
    new_rank = _STATUS_RANK.get(new_status)
    if old_rank is None or new_rank is None:
        return False
    return new_rank < old_rank


def _embed_task_safe(conn: sqlite3.Connection, parsed: ParsedTask) -> None:
    # Fire-and-forget enrichment: missing rag extras / embeddings table /
    # thinking_os on sys.path all degrade to a debug log, never a crash.
    try:
        from embeddings import upsert_embedding
    except ImportError as exc:
        logger.debug("task embedding skipped (module unavailable): %s", exc)
        return

    row = conn.execute("SELECT rowid FROM tasks WHERE task_id = ?", (parsed.task_id,)).fetchone()
    if row is None:
        return

    text_to_embed = " ".join(filter(None, [parsed.title, parsed.outcome]))
    if not text_to_embed.strip():
        return

    try:
        upsert_embedding(conn, "tasks", row[0], text_to_embed)
    except sqlite3.OperationalError as exc:
        logger.debug("task embedding skipped (table missing): %s", exc)
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("task embedding skipped (unexpected): %s", exc)


def sync_one(
    conn: sqlite3.Connection,
    file_path: Path,
    *,
    project_root: Path | None = None,
) -> ParsedTask | None:
    """Sync a single file.  Called by auto-task-sync hook on Write/Edit."""
    content = file_path.read_text(encoding="utf-8")
    duplicate = detect_duplicate_frontmatter(content)
    if duplicate:
        # Two frontmatter blocks with conflicting status silently skew board
        # counts (the parser only reads the first) — reject loudly.
        logger.warning("sync rejected %s: %s", file_path.name, duplicate)
        return None
    parsed = parse_task(content, path=file_path)
    if parsed is None:
        logger.debug("unparseable: %s", file_path)
        return None

    project_root = project_root or Path.cwd()
    try:
        rel_path = str(file_path.resolve().relative_to(project_root.resolve()))
    except ValueError:
        rel_path = str(file_path)

    # Float mtime (sub-second) — an int truncation made two writes within the
    # same second indistinguishable, so sync_all silently skipped the second.
    mtime = file_path.stat().st_mtime
    content_hash = parsed.body_hash

    existing = _fetch_existing(conn, parsed.task_id)
    old_status = existing["status"] if existing else None

    _upsert_task(
        conn,
        parsed,
        file_path=rel_path,
        mtime=mtime,
        content_hash=content_hash,
    )

    if old_status and old_status != parsed.status:
        reason = "file-sync"
        if _is_backward(str(old_status), parsed.status):
            reason = _SYNC_CONFLICT_REASON
            logger.warning(
                "sync conflict on %s: file status %r overrode DB status %r — "
                "backward move outside the workflow (stale revert?)",
                parsed.task_id,
                parsed.status,
                old_status,
            )
        _record_status_change(
            conn,
            parsed.task_id,
            str(old_status),
            parsed.status,
            parsed.agent_session,
            reason=reason,
        )

    _embed_task_safe(conn, parsed)

    conn.commit()
    return parsed


def _prune_missing_tasks(conn: sqlite3.Connection, seen_paths: set[str]) -> int:
    rows = conn.execute("SELECT task_id, file_path FROM tasks").fetchall()
    gone = [r[0] for r in rows if r[1] and r[1] not in seen_paths]
    for task_id in gone:
        conn.execute("DELETE FROM tasks WHERE task_id = ?", (task_id,))
    if gone:
        conn.commit()
    return len(gone)


def sync_all(
    conn: sqlite3.Connection,
    project_root: Path | None = None,
    *,
    force: bool = False,
) -> dict[str, int]:
    """Full sync of docs/tasks/.  Returns counters for observability."""
    project_root = (project_root or Path.cwd()).resolve()
    files = _iter_task_files(project_root)

    stats = {"scanned": 0, "upserted": 0, "skipped_unchanged": 0, "parse_errors": 0, "pruned": 0}
    seen_paths: set[str] = set()

    for path in files:
        stats["scanned"] += 1
        rel_path = str(path.relative_to(project_root))
        seen_paths.add(rel_path)
        if not force:
            mtime = path.stat().st_mtime
            row = conn.execute(
                "SELECT mtime FROM tasks WHERE file_path = ?",
                (rel_path,),
            ).fetchone()
            if row and row[0] == mtime:
                stats["skipped_unchanged"] += 1
                continue
        result = sync_one(conn, path, project_root=project_root)
        if result is None:
            stats["parse_errors"] += 1
        else:
            stats["upserted"] += 1

    # Prune rows whose file vanished — but never from an empty/misdirected walk
    # (a zero-file scan must not wipe the board).
    if stats["scanned"] > 0:
        stats["pruned"] = _prune_missing_tasks(conn, seen_paths)

    return stats
