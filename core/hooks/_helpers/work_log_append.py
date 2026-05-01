"""Append a Work Log entry to a task — called from capture-work-log hook.

USAGE
    python3 work_log_append.py <task_id> <summary>
Reads COS_PROJECT_ROOT, COS_DB_PATH, COS_AGENT_SESSION_ID from env.
"""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        return 0
    task_id, summary = argv[1], argv[2]

    try:
        from board_os.mcp_tools import cos_work_log_append
    except ImportError:
        return 0

    project_root = Path(os.environ.get("COS_PROJECT_ROOT", os.getcwd())).resolve()
    db_path = os.environ.get(
        "COS_DB_PATH", str(project_root / ".coding-os" / "coding-os.db"),
    )
    if not Path(db_path).exists():
        return 0

    conn = sqlite3.connect(db_path)
    try:
        cos_work_log_append(
            conn,
            task_id=task_id,
            summary=summary,
            agent_session=os.environ.get("COS_AGENT_SESSION_ID"),
            source="auto",
        )
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
