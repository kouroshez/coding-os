"""
List in-progress / testing tasks from thinking_os DB for the SessionStart banner.

USAGE
    python3 wip_lines.py <db_path>
"""

from __future__ import annotations

import sqlite3
import sys
import time


def _human(seconds: int | None) -> str:
    # Compact dwell label so a stranded card screams its age on resume.
    if seconds is None:
        return "?"
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h"
    return f"{seconds // 86400}d"


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        return 1
    now = int(time.time())
    try:
        conn = sqlite3.connect(argv[1])
        rows = conn.execute(
            "SELECT task_id, title, status, started_at, "
            "  (SELECT MAX(transitioned_at) FROM task_status_history h "
            "   WHERE h.task_id = tasks.task_id) "
            "FROM tasks "
            "WHERE status IN ('in_progress','testing','emergency') "
            "ORDER BY status DESC, task_id LIMIT 5"
        ).fetchall()
        conn.close()
        for tid, title, status, started_at, last_tx in rows:
            last = max(int(started_at or 0), int(last_tx or 0))
            age = _human(now - last if last else None)
            # Surface status + dwell-age so an inherited zombie is obviously
            # stale at the highest-attention moment (SessionStart resume).
            print(f"  {tid}: {title} ({status} {age})")
    except Exception:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
