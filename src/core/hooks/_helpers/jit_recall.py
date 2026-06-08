#!/usr/bin/env python3
"""PreToolUse just-in-time recall (B2): surface a past lesson relevant to the
file about to be edited. Prints the lesson text to stdout (empty if none).

Match = a `lesson` whose text contains the file's basename (friction lessons
embed the cleaned failure display, which includes the basename for file-scoped
failures). Fast + read-only; any error prints nothing.

USAGE: python3 jit_recall.py <db_path> <file_path>
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path


def relevant_lesson(db_path: str, file_path: str) -> str:
    base = Path(file_path).name
    if not db_path or not base or not Path(db_path).exists():
        return ""
    try:
        conn = sqlite3.connect(db_path, timeout=2)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT pattern FROM learned_patterns "
                "WHERE memory_type = 'lesson' AND archived_at IS NULL AND promoted_to IS NULL "
                "  AND instr(lower(pattern), lower(?)) > 0 "
                "ORDER BY confidence DESC LIMIT 1",
                (base,),
            ).fetchone()
        finally:
            conn.close()
    except sqlite3.Error:
        return ""
    return (row["pattern"] or "")[:200] if row else ""


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        return 0
    try:
        lesson = relevant_lesson(argv[1], argv[2])
    except Exception:  # fire-and-forget — never break the tool call
        return 0
    if lesson:
        print(lesson)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
