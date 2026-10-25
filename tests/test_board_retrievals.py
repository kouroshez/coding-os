"""The task-done brain pipeline must NOT be a hardcoded-'success' writer:
board_commands._record_brain_outcome_safe records the outcome record_outcome
derives, so a reopened task closes as 'rework'."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
for _p in (_ROOT, _ROOT / "src", _ROOT / "src" / "core", _ROOT / "src" / "core" / "thinking_os"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from database import init_db

from cli import board_commands


def test_task_done_records_derived_rework(tmp_path, monkeypatch) -> None:
    db = tmp_path / ".coding-os" / "coding-os.db"
    db.parent.mkdir(parents=True)
    monkeypatch.setenv("COS_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("COS_DB_PATH", str(db))
    conn = init_db(db)
    conn.execute(
        "INSERT INTO task_status_history (task_id, old_status, new_status, transitioned_at) "
        "VALUES ('TASK-7', 'testing', 'in_progress', 0)"
    )
    conn.commit()

    board_commands._record_brain_outcome_safe(conn, "TASK-7")

    outcome = conn.execute("SELECT outcome FROM task_outcomes WHERE task_id='TASK-7'").fetchone()[0]
    conn.close()
    assert outcome == "rework"
