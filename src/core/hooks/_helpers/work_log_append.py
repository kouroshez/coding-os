"""Append a Work Log entry to a task — called from capture-work-log +
link-commit-to-task hooks.

USAGE
    python3 work_log_append.py <task_id> <summary>
Reads COS_PROJECT_ROOT, COS_DB_PATH, COS_AGENT_SESSION_ID from env.
Exit 0 = appended; exit 1 = could not append (callers may log/fall back).
"""

from __future__ import annotations

import fcntl
import json
import os
import sqlite3
import sys
from pathlib import Path

# board_os lives at src/core/ — two levels up from _helpers/. Without this
# bootstrap (every sibling helper has it) the import below fails for any
# hook-spawned python3 and the append was a silent no-op (TASK-340).
_CORE = Path(__file__).resolve().parents[2]
if _CORE.is_dir() and str(_CORE) not in sys.path:
    sys.path.insert(0, str(_CORE))


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        return 1
    task_id, summary = argv[1], argv[2]

    try:
        from board_os.mcp_tools import cos_work_log_append
    except ImportError:
        return 1

    try:
        from thinking_os.database import project_root as _resolve_root  # type: ignore

        project_root = _resolve_root()
    except ImportError:
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
        return 1

    # Cross-platform per-task lock (flock(1) does not exist on macOS — the
    # old bash-side `flock -w 2` died silently there; fcntl works on both).
    lock_dir = project_root / ".coding-os" / "locks"
    try:
        lock_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        return 1
    with open(lock_dir / f"{task_id}.lock", "w", encoding="utf-8") as lock_handle:
        fcntl.flock(lock_handle, fcntl.LOCK_EX)

        # Route through get_connection for WAL + busy_timeout so a concurrent
        # board write waits instead of failing on a locked DB.
        try:
            from thinking_os.database import get_connection  # type: ignore

            conn = get_connection(db_path)
        except Exception:
            conn = sqlite3.connect(db_path, timeout=5.0)
            conn.execute("PRAGMA busy_timeout = 5000")
        try:
            envelope = cos_work_log_append(
                conn,
                task_id=task_id,
                summary=summary,
                agent_session=os.environ.get("COS_AGENT_SESSION_ID"),
                source="auto",
            )
        finally:
            conn.close()
    try:
        appended = bool(json.loads(envelope).get("ok"))
    except (TypeError, ValueError):
        appended = False
    return 0 if appended else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
