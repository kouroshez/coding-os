"""
List in-progress / testing tasks from thinking_os DB for the SessionStart banner.

USAGE
    python3 wip_lines.py <db_path>
"""

from __future__ import annotations

import sqlite3
import sys


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        return 1
    try:
        conn = sqlite3.connect(argv[1])
        rows = conn.execute(
            "SELECT task_id, title FROM tasks "
            "WHERE status IN ('in_progress','testing','emergency') "
            "ORDER BY status DESC, task_id LIMIT 5"
        ).fetchall()
        conn.close()
        for tid, title in rows:
            print(f"  {tid}: {title}")
    except Exception:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
