"""Session startup helper — inject project trajectory context."""

from __future__ import annotations

import json
import sqlite3
import sys


def main(argv: list[str]) -> int:
    if len(argv) < 2 or not argv[1]:
        return 0

    db_path = argv[1]
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        tbl = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='project_trajectory'"
        ).fetchone()
        if not tbl:
            return 0

        row = conn.execute(
            "SELECT phase, current_focus, next_logical_step, open_questions "
            "FROM project_trajectory "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()
        conn.close()

        if not row:
            return 0

        parts = []
        if row["phase"]:
            parts.append(row["phase"])
        if row["current_focus"]:
            parts.append(f"Focus: {row['current_focus']}")
        if row["next_logical_step"]:
            parts.append(f"Next: {row['next_logical_step']}")

        try:
            oqs = json.loads(row["open_questions"] or "[]")
            if oqs and isinstance(oqs, list) and oqs[0]:
                first = oqs[0] if isinstance(oqs[0], str) else oqs[0].get("question", "")
                if first:
                    parts.append(f"Open: {first}")
        except (json.JSONDecodeError, TypeError, AttributeError, KeyError):
            pass  # open_questions is optional decoration — safe to skip on parse error

        if parts:
            print(f"[Project Trajectory] {' · '.join(parts)}")

    except Exception:
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
