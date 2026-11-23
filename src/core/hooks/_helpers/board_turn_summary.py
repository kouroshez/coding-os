"""Render this session's board transitions since the last report as one line.

Usage: board_turn_summary.py <db_path> <agent_session> <cursor_file>
Prints nothing when there is nothing new. Stdlib only: hooks run it with bare python3.
"""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from pathlib import Path

MAX_TASKS_SHOWN = 8
EMERGENCY = "emergency"


def _read_cursor(cursor_file: Path) -> int:
    try:
        return int(cursor_file.read_text(encoding="utf-8").strip() or 0)
    except (OSError, ValueError):
        return 0


def _write_cursor(cursor_file: Path, last_id: int) -> None:
    descriptor, temp_path = tempfile.mkstemp(dir=cursor_file.parent, prefix=".board-cursor.")
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(f"{last_id}\n")
    os.replace(temp_path, cursor_file)


def status_chains(rows: list[tuple[int, str, str, str]]) -> dict[str, list[str]]:
    chains: dict[str, list[str]] = {}
    for _row_id, task_id, old_status, new_status in rows:
        chain = chains.get(task_id)
        if chain is None:
            chains[task_id] = [f"+{new_status}"] if not old_status else [old_status, new_status]
        elif chain[-1].lstrip("+") != new_status:
            chain.append(new_status)
    return chains


def render(chains: dict[str, list[str]]) -> str:
    parts = []
    for task_id, chain in list(chains.items())[:MAX_TASKS_SHOWN]:
        flag = "🚨 " if any(status.lstrip("+") == EMERGENCY for status in chain) else ""
        parts.append(f"{flag}{task_id} {'→'.join(chain)}")
    hidden = len(chains) - MAX_TASKS_SHOWN
    if hidden > 0:
        parts.append(f"+{hidden} more (cos board)")
    return "📋 " + " · ".join(parts)


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        print(__doc__, file=sys.stderr)
        return 2
    db_path, agent_session, cursor_file = argv[1], argv[2], Path(argv[3])
    cursor = _read_cursor(cursor_file)
    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as connection:
        rows = connection.execute(
            "SELECT id, task_id, old_status, new_status FROM task_status_history "
            "WHERE agent_session = ? AND id > ? ORDER BY id",
            (agent_session, cursor),
        ).fetchall()
    if not rows:
        return 0
    print(render(status_chains(rows)))
    _write_cursor(cursor_file, rows[-1][0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
