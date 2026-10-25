"""Stop-hook recap helper — emit a systemMessage line summarizing the
just-finished session: role dispatches fired.
Used by core/hooks/session-end.sh to give the operator a visible end-of-turn
pulse. Bounded — silent on any error.
"""

from __future__ import annotations

import contextlib
import json
import sqlite3
import sys


def _scalar(cursor: sqlite3.Cursor, sql: str, args: tuple) -> int:
    try:
        row = cursor.execute(sql, args).fetchone()
        return int(row[0]) if row and row[0] is not None else 0
    except sqlite3.Error:
        return 0


def _narrate(disp: int) -> str:
    # Deterministic plain-language line — no LLM, one cheap count.
    if disp:
        return f"{disp} role step{'s' if disp != 1 else ''}"
    return "no new cognitive activity this session"


def main() -> int:
    if len(sys.argv) < 3:
        return 0
    db_path, session_id = sys.argv[1], sys.argv[2]
    if not session_id:
        return 0
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
    except sqlite3.Error:
        return 0
    disp = _scalar(
        cur, "SELECT COUNT(*) FROM formula_dispatches WHERE session_id = ?", (session_id,)
    )
    with contextlib.suppress(sqlite3.Error):
        conn.close()

    ses_tail = session_id[-8:]
    text = (
        f"[coding-os recap] {_narrate(disp)} (ses={ses_tail})"
        f" — trace: cos cognition trace {session_id}"
    )
    payload = {"systemMessage": text}
    sys.stdout.write(json.dumps(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
