"""The task-done brain pipeline must NOT be a second hardcoded-'success' writer.
board_commands._record_brain_outcome_safe back-fills retrievals.outcome; the audit
found it stamped a literal 'success' even when record_outcome derived 'rework'. It
now threads the derived outcome through."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
for _p in (_ROOT, _ROOT / "src", _ROOT / "src" / "core", _ROOT / "src" / "core" / "thinking_os"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from cli import board_commands  # noqa: E402
from database import init_db  # noqa: E402


def test_retrievals_backfill_carries_derived_rework(tmp_path, monkeypatch) -> None:
    db = tmp_path / ".coding-os" / "coding-os.db"
    db.parent.mkdir(parents=True)
    monkeypatch.setenv("COS_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("COS_DB_PATH", str(db))
    conn = init_db(db)
    # A reopened task → record_outcome derives 'rework'.
    conn.execute(
        "INSERT INTO task_status_history (task_id, old_status, new_status, transitioned_at) "
        "VALUES ('TASK-7', 'testing', 'in_progress', 0)"
    )
    # A retrieval citing that task with a NULL outcome (the back-fill target).
    conn.execute(
        "INSERT INTO retrievals (session_id, task_id, layer, query, source_table, source_id, outcome) "
        "VALUES ('s', 'TASK-7', 'memory', 'q', 'observations', 1, NULL)"
    )
    conn.commit()

    board_commands._record_brain_outcome_safe(conn, "TASK-7")

    outcome = conn.execute("SELECT outcome FROM task_outcomes WHERE task_id='TASK-7'").fetchone()[0]
    retr = conn.execute("SELECT outcome FROM retrievals WHERE task_id='TASK-7'").fetchone()[0]
    conn.close()
    assert outcome == "rework"  # derived from the reopen, not hardcoded success
    assert retr == "rework"  # back-fill carried the derived outcome, not a 2nd 'success'
