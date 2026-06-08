"""Tests for the B1 auto-validation helper (src/core/hooks/_helpers/auto_validate_lessons.py).

Closes the learn->apply->confirm loop: surfaced lessons whose failure recurs in
the session validate as not-helpful; those with no recurrence validate helpful.
"""

from __future__ import annotations

import os
import sqlite3
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # thinking_os
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "hooks" / "_helpers"))

from auto_validate_lessons import auto_validate  # noqa: E402
from database import init_db  # noqa: E402

# A real-shaped friction lesson: the cleaned failure display is embedded in the
# text, so a recurring failure's cluster key is a contiguous substring.
LESSON = (
    "Recurring completion gap (2 occurrences): task_not_closed: TASK-N is still "
    "testing at session end -> resolve the gap"
)


def _seed_lesson(db: Path, text: str, conf: float = 0.6) -> int:
    conn = sqlite3.connect(str(db))
    try:
        conn.execute(
            "INSERT INTO learned_patterns (pattern, memory_type, confidence) VALUES (?, 'lesson', ?)",
            (text, conf),
        )
        conn.commit()
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    finally:
        conn.close()


def _suggestions(tmp_path: Path, pid: int, text: str) -> Path:
    f = tmp_path / ".learn-suggestions"
    f.write_text(f"{pid}\t{text}\n", encoding="utf-8")
    old = time.time() - 60  # recall happened a minute ago
    os.utime(f, (old, old))
    return f


@pytest.fixture
def db(tmp_path: Path) -> Path:
    p = tmp_path / "test.db"
    init_db(p).close()
    return p


def test_helpful_when_no_recurrence(db: Path, tmp_path: Path) -> None:
    pid = _seed_lesson(db, LESSON)
    f = _suggestions(tmp_path, pid, LESSON)
    res = auto_validate("ses-t", str(db), str(f))
    assert res["status"] == "ok"
    assert res["helpful"] == 1 and res["unhelpful"] == 0
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT times_validated FROM learned_patterns WHERE id=?", (pid,)).fetchone()
    conn.close()
    assert row["times_validated"] >= 1


def test_unhelpful_when_failure_recurs(db: Path, tmp_path: Path) -> None:
    pid = _seed_lesson(db, LESSON)
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO observations (session_id, tool_name, observation_type, memory_type, "
        "impact_score, title, narrative, content_hash) "
        "VALUES ('ses-t','Edit','tool_failure','error',0.6,'gap', "
        "'task_not_closed: TASK-218 is still testing at session end', 'avc1')"
    )
    conn.commit()
    conn.close()
    f = _suggestions(tmp_path, pid, LESSON)
    res = auto_validate("ses-t", str(db), str(f))
    assert res["unhelpful"] == 1 and res["helpful"] == 0
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT times_violated FROM learned_patterns WHERE id=?", (pid,)).fetchone()
    conn.close()
    assert row["times_violated"] >= 1


def test_other_session_failure_ignored(db: Path, tmp_path: Path) -> None:
    pid = _seed_lesson(db, LESSON)
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO observations (session_id, tool_name, observation_type, memory_type, "
        "impact_score, title, narrative, content_hash) "
        "VALUES ('OTHER','Edit','tool_failure','error',0.6,'gap', "
        "'task_not_closed: TASK-218 is still testing at session end', 'avc2')"
    )
    conn.commit()
    conn.close()
    f = _suggestions(tmp_path, pid, LESSON)
    res = auto_validate("ses-t", str(db), str(f))
    assert res["helpful"] == 1  # another session's failure must not penalize


def test_missing_file_is_safe(db: Path, tmp_path: Path) -> None:
    assert auto_validate("ses-t", str(db), str(tmp_path / "nope"))["status"] == "skipped"


def test_empty_suggestions_safe(db: Path, tmp_path: Path) -> None:
    f = tmp_path / ".learn-suggestions"
    f.write_text("", encoding="utf-8")
    assert auto_validate("ses-t", str(db), str(f))["status"] == "no_suggestions"
