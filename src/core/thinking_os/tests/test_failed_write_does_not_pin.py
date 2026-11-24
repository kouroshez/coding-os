"""A write that loses a lock race must not leave its connection pinning the WAL.

Python's sqlite3 opens an implicit BEGIN before a DML; when the DML fails and
nothing rolls back, the connection stays in that transaction, its next read
takes a snapshot no checkpoint can pass, and every later write fails with
BUSY_SNAPSHOT. That pinned a 9.87 GB WAL (state-files.md § WAL size discipline).
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import get_pooled_conn, init_db
from tools._shared import safe_tool


@pytest.fixture()
def db_path(tmp_path: Path) -> str:
    path = str(tmp_path / "pin.db")
    init_db(path)
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE notes (body TEXT)")
    conn.commit()
    conn.close()
    return path


def _checkpoint_is_complete(path: str) -> bool:
    probe = sqlite3.connect(path)
    try:
        _busy, log_frames, checkpointed = probe.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone()
    finally:
        probe.close()
    return log_frames == checkpointed


def test_a_write_that_loses_the_lock_race_leaves_nothing_pinned(db_path: str) -> None:
    pooled = get_pooled_conn(db_path)
    pooled.execute("PRAGMA busy_timeout = 20")
    rival = sqlite3.connect(db_path, isolation_level=None)
    rival.execute("BEGIN IMMEDIATE")

    @safe_tool
    def cos_write_note() -> str:
        get_pooled_conn(db_path).execute("INSERT INTO notes VALUES ('lost')")
        get_pooled_conn(db_path).commit()
        return "{}"

    @safe_tool
    def cos_read_notes() -> str:
        get_pooled_conn(db_path).execute("SELECT count(*) FROM notes").fetchone()
        return "{}"

    assert '"ok": false' in cos_write_note()
    rival.execute("INSERT INTO notes VALUES ('rival')")
    rival.execute("COMMIT")
    cos_read_notes()

    assert not pooled.in_transaction
    assert _checkpoint_is_complete(db_path)
    assert '"ok": false' not in cos_write_note()


def test_an_inner_tool_never_ends_its_callers_transaction(db_path: str) -> None:
    @safe_tool
    def cos_inner() -> str:
        return "{}"

    @safe_tool
    def cos_outer() -> str:
        conn = get_pooled_conn(db_path)
        conn.execute("INSERT INTO notes VALUES ('outer')")
        cos_inner()
        assert conn.in_transaction, "the inner tool rolled back its caller's transaction"
        conn.commit()
        return "{}"

    assert '"ok": false' not in cos_outer()
    assert get_pooled_conn(db_path).execute("SELECT count(*) FROM notes").fetchone()[0] == 1
