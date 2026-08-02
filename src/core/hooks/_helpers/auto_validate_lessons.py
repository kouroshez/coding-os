#!/usr/bin/env python3
"""Auto-validate surfaced lessons at task-done — closes the learn->apply->confirm
loop without the agent volunteering cos_learn_validate (B1).

Called by remind-learn-validate.sh on `cos task-done`. A thin CLI adapter over
`tools.learning.validate_surfaced_lessons`, the single primitive the MCP
completion path (board_os) also calls — so the loop closes identically whichever
way a task is finished. Fire-and-forget: any error exits 0 and leaves the
reminder intact.

USAGE: python3 auto_validate_lessons.py <session_id> <db_path> <suggestions_file>
"""

from __future__ import annotations

import sys
from pathlib import Path

_THINKING_OS = Path(__file__).resolve().parents[1] / "thinking_os"
if _THINKING_OS.is_dir() and str(_THINKING_OS) not in sys.path:
    sys.path.insert(0, str(_THINKING_OS))


def auto_validate(session_id: str, db_path: str, suggestions_file: str) -> dict:
    sf = Path(suggestions_file)
    if not session_id or not db_path or not sf.exists():
        return {"status": "skipped"}

    from database import get_connection
    from tools.learning import validate_surfaced_lessons

    conn = get_connection(db_path)
    try:
        return validate_surfaced_lessons(conn, session_id=session_id, suggestions_path=str(sf))
    finally:
        conn.close()


def main(argv: list[str]) -> int:
    if len(argv) < 4:
        return 0
    try:
        result = auto_validate(argv[1], argv[2], argv[3])
    except Exception:  # fire-and-forget — never break the task-done hook
        return 0
    if result.get("status") == "ok":
        print(
            f"auto-validated {result['surfaced']} surfaced lesson(s): "
            f"{result['helpful']} helpful, {result['unhelpful']} not"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
