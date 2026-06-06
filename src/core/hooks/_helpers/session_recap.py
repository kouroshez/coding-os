"""Stop-hook recap helper — emit hookSpecificOutput JSON block summarizing
the just-finished session: observations captured, dispatches fired, backtracks.
Used by core/hooks/session-end.sh to give the operator a visible end-of-turn
pulse, mirroring the always-on caveman pattern. Bounded — silent on any error.
"""

from __future__ import annotations

import json
import sqlite3
import sys


def _scalar(cursor: sqlite3.Cursor, sql: str, args: tuple) -> int:
    try:
        row = cursor.execute(sql, args).fetchone()
        return int(row[0]) if row and row[0] is not None else 0
    except sqlite3.Error:
        return 0


def _narrate(obs: int, disp: int, bt: int) -> str:
    # Deterministic plain-language line — no LLM, same cheap counts. Reads as a
    # session accomplishment ("34 insights captured, clean run") instead of the
    # cryptic obs=N dispatch=N backtrack=N that taught operators to ignore it.
    bits = []
    if obs:
        bits.append(f"{obs} insight{'s' if obs != 1 else ''} captured")
    if disp:
        bits.append(f"{disp} role step{'s' if disp != 1 else ''}")
    if bt:
        bits.append(f"{bt} backtrack{'s' if bt != 1 else ''}")
    elif obs or disp:
        bits.append("clean run")
    return ", ".join(bits) if bits else "no new cognitive activity this session"


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
    obs = _scalar(cur, "SELECT COUNT(*) FROM observations WHERE session_id = ?", (session_id,))
    disp = _scalar(
        cur, "SELECT COUNT(*) FROM formula_dispatches WHERE session_id = ?", (session_id,)
    )
    bt = _scalar(cur, "SELECT COUNT(*) FROM backtrack_events WHERE session_id = ?", (session_id,))
    try:
        conn.close()
    except sqlite3.Error:
        pass

    ses_tail = session_id[-8:]
    text = (
        f"[coding-os recap] {_narrate(obs, disp, bt)} (ses={ses_tail})"
        f" — trace: cos cognition trace {session_id}"
    )
    payload = {"systemMessage": text}
    sys.stdout.write(json.dumps(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
