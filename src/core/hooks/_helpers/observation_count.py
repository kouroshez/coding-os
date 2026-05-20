"""Count observations recorded in this session.

USAGE
    python3 observation_count.py <db_path> <session_id>
"""

from __future__ import annotations

import sqlite3
import sys


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(-1)
        return 0
    try:
        conn = sqlite3.connect(argv[1], timeout=2)
        cur = conn.execute(
            "SELECT COUNT(*) FROM observations WHERE session_id = ?",
            (argv[2],),
        )
        print(cur.fetchone()[0])
        conn.close()
    except Exception:
        print(-1)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
