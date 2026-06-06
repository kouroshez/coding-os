"""Sync a Scrumban task file into the thinking_os DB (fire-and-forget).

USAGE
    python3 task_sync.py <task_file_path>
Reads COS_PROJECT_ROOT and COS_DB_PATH from env.
"""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        return 0
    try:
        from board_os.sync import sync_one
    except ImportError:
        return 0

    file_path = Path(argv[1])
    if not file_path.exists():
        return 0

    project_root = Path(os.environ.get("COS_PROJECT_ROOT", os.getcwd())).resolve()
    try:
        from thinking_os.database import resolve_db_path  # type: ignore

        db_path = str(resolve_db_path(project_root))
    except ImportError:
        db_path = os.environ.get(
            "COS_DB_PATH",
            str(project_root / ".coding-os" / "coding-os.db"),
        )
    if not Path(db_path).exists():
        return 0

    # Route through get_connection for WAL + busy_timeout (TASK-108).
    try:
        from thinking_os.database import get_connection  # type: ignore

        conn = get_connection(db_path)
    except Exception:
        conn = sqlite3.connect(db_path, timeout=5.0)
        conn.execute("PRAGMA busy_timeout = 5000")
    try:
        sync_one(conn, file_path, project_root=project_root)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
