#!/usr/bin/env python3
"""Emit a one-line reason when a session shows real learning signal — rework
churn (a file edited >=3x) or a backtrack — else nothing. Used by
nudge-learn-narrative.sh to decide whether to nudge a lesson recording.

Usage: narrative_signal.py <db_path> <session_id>
"""

from __future__ import annotations

import sqlite3
import sys

_CHURN_MIN = 3  # a file edited this many times in one session = rework churn


def main() -> int:
    if len(sys.argv) < 3:
        return 0
    db_path, session = sys.argv[1], sys.argv[2]
    if not session:
        return 0
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
    except sqlite3.Error:
        return 0
    try:
        # 1. rework churn — same file edited >= _CHURN_MIN times this session
        try:
            row = conn.execute(
                "SELECT files_modified AS f, COUNT(*) AS c FROM observations "
                "WHERE session_id = ? AND files_modified IS NOT NULL AND files_modified != '' "
                "GROUP BY files_modified HAVING c >= ? ORDER BY c DESC LIMIT 1",
                (session, _CHURN_MIN),
            ).fetchone()
        except sqlite3.OperationalError:
            row = None
        if row and row["f"]:
            print(f"reworked {row['f'].rsplit('/', 1)[-1]} {row['c']}x")
            return 0
        # 2. a recorded backtrack this session
        try:
            r = conn.execute(
                "SELECT COUNT(*) AS c FROM backtrack_events WHERE session_id = ?",
                (session,),
            ).fetchone()
            if r and r["c"]:
                print(f"{r['c']} backtrack(s) this session")
                return 0
        except sqlite3.OperationalError:
            pass
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
