"""Unit coverage for the JIT-recall helper (jit-recall.sh's matcher).

Regression guard for the audit finding: the matcher keyed on basename-in-lesson
-text and matched 0 of 4 live lessons. It now keys on the `file:<basename>`
concept token minted by learning._mine_friction_lessons.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src" / "core" / "thinking_os"))
sys.path.insert(0, str(_ROOT / "src" / "core" / "hooks" / "_helpers"))

from database import init_db  # noqa: E402
from jit_recall import relevant_lesson  # noqa: E402

_INS = (
    "INSERT INTO learned_patterns (pattern, memory_type, source, confidence, concepts) "
    "VALUES (?, 'lesson', 'friction', 0.6, ?)"
)


def _db(tmp_path: Path):
    db = tmp_path / "db.sqlite"
    conn = init_db(db)
    conn.execute(
        _INS,
        (
            "Recurring hook block (3 occurrences): editing core without skill -> load it",
            '["lesson", "hook_block", "friction", "file:widget.py"]',
        ),
    )
    conn.commit()
    conn.close()
    return db


def test_matches_via_file_concept(tmp_path: Path) -> None:
    db = _db(tmp_path)
    out = relevant_lesson(str(db), "/abs/path/to/widget.py")
    assert "editing core without skill" in out  # matched by file:widget.py concept


def test_no_match_for_unrelated_file(tmp_path: Path) -> None:
    db = _db(tmp_path)
    assert relevant_lesson(str(db), "/abs/path/other.py") == ""


def test_missing_db_silent(tmp_path: Path) -> None:
    assert relevant_lesson(str(tmp_path / "nope.db"), "widget.py") == ""
