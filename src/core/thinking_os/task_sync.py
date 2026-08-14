"""
Coding OS — Task store sync (compatibility shim).

The legacy v6 sync (own parser + `docs/tasks.md` status index + v6-only
columns) was retired in TASK-398. `board_os/sync.py` is the SOLE
tasks-table writer; every legacy entry point delegates to it so existing
callers keep working unchanged:

    sync_tasks(conn, project_root, ...) — CLI/daemon/tests entry point
    sync(conn, project_root=...)        — background.py runner alias
    python task_sync.py --project-root … --db … [--force]

Files remain SSOT — this module never writes markdown.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path


def _board_sync_all(conn: sqlite3.Connection, project_root: Path, force: bool) -> dict:
    core_dir = Path(__file__).resolve().parent.parent
    if str(core_dir) not in sys.path:
        sys.path.insert(0, str(core_dir))
    from board_os.sync import sync_all

    stats = sync_all(conn, project_root=project_root, force=force)
    # Legacy stat aliases — pre consumers (verify_phase_c_e2e.py)
    # read new/errors/skipped.
    stats.setdefault("new", stats.get("upserted", 0))
    stats.setdefault("errors", stats.get("parse_errors", 0))
    stats.setdefault("skipped", stats.get("skipped_unchanged", 0))
    return stats


def sync_tasks(
    conn: sqlite3.Connection,
    project_root: Path | str,
    tasks_dir: Path | None = None,
    index_file: Path | None = None,
    force: bool = False,
) -> dict:
    return _board_sync_all(conn, Path(project_root), bool(force))


# background.py's runner calls task_sync.sync(...) — keep both names bound
# to the one implementation.
sync = sync_tasks


def _main() -> None:
    parser = argparse.ArgumentParser(description="Sync docs/tasks/ → coding-os.db (board_os sync)")
    parser.add_argument("--project-root", type=str, default=".")
    parser.add_argument("--db", type=str, default=None)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    from database import init_db

    conn = init_db(args.db)
    try:
        stats = sync_tasks(conn, Path(args.project_root).resolve(), force=args.force)
    finally:
        conn.close()
    print(json.dumps({"status": "ok", "stats": stats}))


if __name__ == "__main__":
    _main()
