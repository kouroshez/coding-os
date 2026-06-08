"""record_outcome refines an optimistic 'success' into the honest 'rework' from
the task's OWN history (reopen via task_status_history, backtrack in the closing
session). That non-monotone signal is the only thing that un-suppresses the
variance-gated learning extractors — without it every outcome was 'success' and
learn_extract minted almost nothing (192 tasks → 4 patterns)."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import init_db  # noqa: E402
from record_outcome import _derive_rework, record_outcome  # noqa: E402


def _reopen(db: Path, task_id: str) -> None:
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO task_status_history (task_id, old_status, new_status, transitioned_at) "
        "VALUES (?, 'testing', 'in_progress', 0)",
        (task_id,),
    )
    conn.commit()
    conn.close()


@pytest.fixture
def db(tmp_path: Path) -> Path:
    p = tmp_path / ".coding-os" / "coding-os.db"
    p.parent.mkdir(parents=True)
    init_db(p).close()
    return p


class TestDeriveRework:
    """Scenario coverage: clean / reopened / backtracked / explicit-non-success /
    refine-disabled — across the CLI task-done and MCP completion personas (both
    route through record_outcome)."""

    def test_clean_task_stays_success(self, db: Path) -> None:
        r = record_outcome(task_id="TASK-1", task_type="feat", outcome="success", db_path=db)
        assert r["outcome"] == "success"

    def test_reopened_task_becomes_rework(self, db: Path) -> None:
        _reopen(db, "TASK-2")
        r = record_outcome(task_id="TASK-2", task_type="fix", outcome="success", db_path=db)
        assert r["outcome"] == "rework"

    def test_backtrack_does_not_smear_to_rework(
        self, db: Path, tmp_path: Path, monkeypatch
    ) -> None:
        # Regression: backtrack was dropped as a signal because it is session-
        # scoped with no task_id — a single backtrack in a high-fanout closing
        # session would smear EVERY task closed in that session to 'rework'. A
        # clean (non-reopened) task closed in a session that has a backtrack must
        # stay 'success'.
        sess = "ses-claude-test-smear"
        sfile = tmp_path / "session-id"
        sfile.write_text(sess)
        monkeypatch.setenv("COS_SESSION_FILE", str(sfile))
        conn = sqlite3.connect(str(db))
        conn.execute(
            "INSERT INTO backtrack_events (session_id, from_formula, to_formula, reason) "
            "VALUES (?, 'a', 'b', 'redo')",
            (sess,),
        )
        conn.commit()
        conn.close()
        r = record_outcome(task_id="TASK-CLEAN", task_type="fix", outcome="success", db_path=db)
        assert r["outcome"] == "success"  # no smear — backtrack is not a rework signal

    def test_explicit_nonsuccess_not_overridden(self, db: Path) -> None:
        _reopen(db, "TASK-4")  # has reopen signal, but caller asserts 'blocked'
        r = record_outcome(task_id="TASK-4", task_type="fix", outcome="blocked", db_path=db)
        assert r["outcome"] == "blocked"  # refine only upgrades an optimistic 'success'

    def test_refine_disabled_keeps_success(self, db: Path) -> None:
        _reopen(db, "TASK-5")
        r = record_outcome(
            task_id="TASK-5", task_type="fix", outcome="success",
            refine_from_history=False, db_path=db,
        )
        assert r["outcome"] == "success"

    def test_derive_helper_false_on_clean(self, db: Path) -> None:
        conn = sqlite3.connect(str(db))
        try:
            assert _derive_rework(conn, "UNKNOWN-TASK") is False
        finally:
            conn.close()
