#!/usr/bin/env python3
"""
Thinking OS — Record post-task review to session_summaries (TASK-137).

Dual-write: DB primary, fallback to $COS_STATE_DIR/learnings/TASK-###-review.md.
Called by agent after task-done as optional enrichment.

Usage:
    python record_review.py --task TASK-137 --request "..." --investigated "..." \
        --learned "..." --completed "..." --next-steps "..."
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from database import DEFAULT_DB_PATH, get_connection

from core.logging_os import setup as _logging_os_setup

_logging_os_setup(level="info")
logger = logging.getLogger("thinking_os.review")

LEARNINGS_DIR = Path(os.environ.get("COS_STATE_DIR", ".coding-os") + "/learnings")


def _read_session_id() -> str | None:
    """Read session ID from $COS_STATE_DIR/session-id file if it exists."""
    session_file = Path(os.environ.get("COS_STATE_DIR", ".coding-os") + "/session-id")
    if session_file.exists():
        return session_file.read_text().strip() or None
    return None


def record_review(
    *,
    task_id: str,
    request: str = "",
    investigated: str = "",
    learned: str = "",
    completed: str = "",
    next_steps: str = "",
    db_path: str | Path | None = None,
    learnings_dir: str | Path | None = None,
) -> dict:
    """Record a post-task review.

    Tries DB first, falls back to file if DB absent.

    Args:
        task_id: Task identifier (e.g. "TASK-137").
        request: What was asked.
        investigated: What was explored.
        learned: Key insight.
        completed: What was done.
        next_steps: Followup.
        db_path: Path to DB. Defaults to DEFAULT_DB_PATH.
        learnings_dir: Path to learnings directory for fallback.

    Returns:
        Dict with status and write location.
    """
    path = Path(db_path or DEFAULT_DB_PATH)
    fallback_dir = Path(learnings_dir or LEARNINGS_DIR)

    if path.exists():
        return _write_to_db(
            path, task_id=task_id, request=request,
            investigated=investigated, learned=learned,
            completed=completed, next_steps=next_steps,
        )
    else:
        return _write_fallback_file(
            fallback_dir, task_id=task_id, request=request,
            investigated=investigated, learned=learned,
            completed=completed, next_steps=next_steps,
        )


def _write_to_db(
    db_path: Path,
    *,
    task_id: str,
    request: str,
    investigated: str,
    learned: str,
    completed: str,
    next_steps: str,
) -> dict:
    """Write review to session_summaries table."""
    session_id = _read_session_id()
    conn = get_connection(db_path)
    try:
        # Each review is a historical event — we INSERT a new row rather than
        # overwriting. A task may legitimately have multiple reviews
        # (e.g. first attempt + after rework). session_summary.py keeps its
        # own metadata row per session; review rows live alongside it.
        cursor = conn.execute(
            "INSERT INTO session_summaries "
            "(session_id, task_id, request, investigated, learned, completed, next_steps) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (session_id, task_id, request, investigated, learned, completed, next_steps),
        )
        conn.commit()
        row_id = cursor.lastrowid
        logger.info("Recorded review for %s to DB (id=%d)", task_id, row_id)
        return {"status": "recorded", "target": "db", "id": row_id}
    finally:
        conn.close()


def _write_fallback_file(
    learnings_dir: Path,
    *,
    task_id: str,
    request: str,
    investigated: str,
    learned: str,
    completed: str,
    next_steps: str,
) -> dict:
    """Write review to a markdown file as fallback."""
    learnings_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{task_id}-review.md"
    filepath = learnings_dir / filename

    content = (
        f"---\n"
        f"task_id: {task_id}\n"
        f"date: {date.today().isoformat()}\n"
        f"---\n\n"
        f"## Request\n\n{request or '(not recorded)'}\n\n"
        f"## Investigated\n\n{investigated or '(not recorded)'}\n\n"
        f"## Learned\n\n{learned or '(not recorded)'}\n\n"
        f"## Completed\n\n{completed or '(not recorded)'}\n\n"
        f"## Next Steps\n\n{next_steps or '(not recorded)'}\n"
    )

    filepath.write_text(content)
    logger.info("Recorded review for %s to %s (DB absent)", task_id, filepath)
    return {"status": "recorded", "target": "file", "path": str(filepath)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Record post-task review")
    parser.add_argument("--task", required=True, help="Task ID")
    parser.add_argument("--request", default="", help="What was asked")
    parser.add_argument("--investigated", default="", help="What was explored")
    parser.add_argument("--learned", default="", help="Key insight")
    parser.add_argument("--completed", default="", help="What was done")
    parser.add_argument("--next-steps", default="", help="Followup")
    args = parser.parse_args()

    result = record_review(
        task_id=args.task,
        request=args.request,
        investigated=args.investigated,
        learned=args.learned,
        completed=args.completed,
        next_steps=args.next_steps,
    )

    if result["target"] == "db":
        print(f"Review recorded to DB (id={result['id']})")
    else:
        print(f"Review recorded to {result['path']} (DB absent)")


if __name__ == "__main__":
    main()
