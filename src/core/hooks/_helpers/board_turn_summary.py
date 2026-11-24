"""Describe this session's task creates and moves since the last report, one plain line each.

Usage: board_turn_summary.py <db_path> <agent_session> <cursor_file>
Prints nothing when there is nothing new. Stdlib only: hooks run it with bare python3.
"""

from __future__ import annotations

import os
import re
import sqlite3
import sys
import tempfile
from pathlib import Path

MAX_EVENTS_SHOWN = 10
TITLE_CHARS = 48
COMMIT_PREFIX = re.compile(r"^[a-z]+(\([^)]*\))?!?:\s*")
# Line breaks, C0/C1 controls and bidi overrides: in a title any of them could
# start a forged event line or reorder what the user reads.
UNPRINTABLE = re.compile(r"[\x00-\x1f\x7f-\x9f  ‪-‮⁦-⁩]")
MOVES = {
    "testing": ("🧪", "moved to testing"),
    "complete": ("✅", "completed"),
    "blocked": ("⛔", "blocked"),
    "emergency": ("🚨", "moved to EMERGENCY"),
    "icebox": ("↩️", "moved back to icebox"),
    "archive": ("📦", "archived"),
}


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


def describe(old_status: str, new_status: str) -> tuple[str, str]:
    if not old_status:
        if new_status == "emergency":
            return "🚨", "created as EMERGENCY"
        return "🆕", f"created in {new_status.replace('_', ' ')}"
    if new_status == "in_progress":
        if old_status == "testing":
            return "🔁", "back in progress (rework)"
        return "▶️", "started (in progress)"
    return MOVES.get(new_status, ("•", f"moved to {new_status.replace('_', ' ')}"))


def short_title(title: str) -> str:
    title = COMMIT_PREFIX.sub("", " ".join(UNPRINTABLE.sub(" ", title).split()))
    return title if len(title) <= TITLE_CHARS else title[: TITLE_CHARS - 1].rstrip() + "…"


def render(rows: list[tuple[int, str, str, str, str]]) -> str:
    lines = []
    for _row_id, task_id, old_status, new_status, title in rows[:MAX_EVENTS_SHOWN]:
        icon, verb = describe(old_status, new_status)
        name = short_title(title)
        lines.append(f"{icon} {task_id} {verb}" + (f" — {name}" if name else ""))
    hidden = len(rows) - MAX_EVENTS_SHOWN
    if hidden > 0:
        lines.append(f"… and {hidden} more (cos board)")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        print(__doc__, file=sys.stderr)
        return 2
    db_path, agent_session, cursor_file = argv[1], argv[2], Path(argv[3])
    cursor = _read_cursor(cursor_file)
    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as connection:
        rows = connection.execute(
            "SELECT h.id, h.task_id, h.old_status, h.new_status, COALESCE(t.title, '') "
            "FROM task_status_history h LEFT JOIN tasks t ON t.task_id = h.task_id "
            "WHERE h.agent_session = ? AND h.id > ? ORDER BY h.id",
            (agent_session, cursor),
        ).fetchall()
    if not rows:
        return 0
    print(render(rows))
    _write_cursor(cursor_file, rows[-1][0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
