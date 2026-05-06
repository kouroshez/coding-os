"""Daemonised fire-and-forget task sync (Phase C enrichment)."""

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
