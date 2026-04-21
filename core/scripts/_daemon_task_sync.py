"""Daemonised fire-and-forget task sync (Phase C enrichment).

PURPOSE:      Called by task-create.sh after a new task file is written.
              Double-forks so the grandchild has no controlling terminal
              and no inherited fds, then runs `sync_tasks()` against the
              thinking-os DB. The parent shell returns immediately — even
              when invoked under `subprocess.Popen(..., capture_output=True)`
              (as pytest does), which is the bug that caused TASK-030 to
              time out.

INPUT:        env → COS_BRAIN_DIR (optional), COS_DB_PATH (optional)
OUTPUT:       none — all stdout/stderr redirected to /dev/null post-daemonise
DEPENDENCIES: thinking-os db.init_db + task_sync.sync_tasks (best-effort;
              absence is silently tolerated per Phase C "enrichment only")
NOTES:        Invoked via `python3 core/scripts/_daemon_task_sync.py >/dev/null
              2>&1 </dev/null`. The parent exits ~instantly after the first
              fork; the grandchild owns the real work.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _daemonise() -> None:
    """Classic double-fork to fully detach from the caller."""
    if os.fork() != 0:
        os._exit(0)
    os.setsid()
    if os.fork() != 0:
        os._exit(0)
    devnull = os.open(os.devnull, os.O_RDWR)
    for fd in (0, 1, 2):
        try:
            os.dup2(devnull, fd)
        except OSError:
            pass


def _sync() -> None:
    try:
        brain_dir = os.environ.get(
            "COS_BRAIN_DIR",
            str(Path(__file__).resolve().parent.parent / "thinking_os"),
        )
        sys.path.insert(0, brain_dir)
        from db import init_db
        from task_sync import sync_tasks
        conn = init_db(os.environ.get("COS_DB_PATH"))
        sync_tasks(conn, project_root=Path.cwd())
        conn.close()
    except Exception:
        # Phase C sync is enrichment only — never block or raise.
        pass


if __name__ == "__main__":
    _daemonise()
    _sync()
