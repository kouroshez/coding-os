"""run_migrations must hold its write lock for the whole apply loop.

Critical Rule 9 § Concurrency contract. The lock was documented but not held:
`BEGIN IMMEDIATE` was followed by a version read that re-entered
`_ensure_version_table()`, whose `conn.commit()` ended the transaction — so
every statement after it autocommitted and a sibling process could migrate the
same DB at the same time. Reading the code could not show that; only executing
it could, which is why these tests assert on `in_transaction` and on a second
connection's ability to take the lock.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import (
    _exec_script_locked,
    _MigrationConnection,
    _split_sql_statements,
    get_schema_version,
    run_migrations,
)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "coding-os.db"


def _rival_can_take_write_lock(db_path: Path) -> bool:
    rival = sqlite3.connect(db_path, timeout=0.1)
    try:
        rival.execute("BEGIN IMMEDIATE")
        return True
    except sqlite3.OperationalError:
        return False
    finally:
        rival.close()


def test_lock_is_held_before_the_first_migration_body_runs(db_path: Path) -> None:
    """The defect window is between BEGIN IMMEDIATE and the first write.

    A probe appended after the real migration list would not see it: their
    INSERTs re-open an implicit transaction, so the lock looks held again by
    then. MIGRATIONS is replaced wholesale so the probe is the very first thing
    to run after the version read — exactly where the lock used to be dropped.
    """
    conn = sqlite3.connect(db_path)
    rival_locked: list[bool] = []

    def probe(migration_conn: object) -> None:
        rival_locked.append(_rival_can_take_write_lock(db_path))
        migration_conn.execute("CREATE TABLE IF NOT EXISTS probe_marker (id INTEGER)")
        migration_conn.commit()  # historical bodies do this — must be inert here

    import database as db_module

    original = list(db_module.MIGRATIONS)
    db_module.MIGRATIONS[:] = [(1, "probe", probe)]
    try:
        run_migrations(conn)
    finally:
        db_module.MIGRATIONS[:] = original

    assert rival_locked == [False], "a second connection took the write lock mid-migration"
    conn.close()


def test_loop_never_calls_executescript_on_the_real_connection(db_path: Path) -> None:
    """`executescript` commits any pending transaction before it runs.

    An end-to-end probe cannot see that window: the `INSERT OR IGNORE` that
    records the version re-opens an implicit transaction straight after, so the
    lock looks held again by the next migration. The invariant is therefore
    asserted where it is decidable — the loop must route scripts through
    `_exec_script_locked`, never through the connection's own executescript.
    """

    class Spy:
        def __init__(self, conn: sqlite3.Connection) -> None:
            self._conn = conn
            self.executescript_calls = 0

        def executescript(self, script: str) -> sqlite3.Cursor:
            self.executescript_calls += 1
            return self._conn.executescript(script)

        def __getattr__(self, name: str) -> object:
            return getattr(self._conn, name)

    conn = sqlite3.connect(db_path)
    spy = Spy(conn)
    import database as db_module

    original = list(db_module.MIGRATIONS)
    db_module.MIGRATIONS[:] = [(1, "script", "CREATE TABLE s1 (x INTEGER);")]
    try:
        run_migrations(spy)
    finally:
        db_module.MIGRATIONS[:] = original

    assert spy.executescript_calls == 0, "script migration bypassed _exec_script_locked"
    assert conn.execute("SELECT 1 FROM sqlite_master WHERE name='s1'").fetchone()
    conn.close()


def test_second_migrator_defers_instead_of_running_unlocked(db_path: Path) -> None:
    holder = sqlite3.connect(db_path)
    holder.execute(
        "CREATE TABLE IF NOT EXISTS schema_version ("
        " version INTEGER PRIMARY KEY, description TEXT,"
        " applied_at DATETIME DEFAULT CURRENT_TIMESTAMP)"
    )
    holder.commit()
    holder.execute("BEGIN IMMEDIATE")

    latecomer = sqlite3.connect(db_path, timeout=0.1)
    import database as db_module

    original_timeout = db_module._MIGRATION_LOCK_TIMEOUT_MS
    db_module._MIGRATION_LOCK_TIMEOUT_MS = 100
    try:
        assert run_migrations(latecomer) == []
    finally:
        db_module._MIGRATION_LOCK_TIMEOUT_MS = original_timeout
        holder.rollback()
        holder.close()
        latecomer.close()


def test_migrations_apply_and_are_idempotent(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    applied = run_migrations(conn)
    assert applied, "expected a fresh DB to apply migrations"
    version = get_schema_version(conn)

    second = sqlite3.connect(db_path)
    assert run_migrations(second) == []
    assert get_schema_version(second) == version
    conn.close()
    second.close()


def test_split_keeps_trigger_bodies_and_quoted_semicolons_intact() -> None:
    script = (
        "CREATE TABLE t (id INTEGER, v TEXT);\n"
        "CREATE TRIGGER t_ai AFTER INSERT ON t\n"
        "BEGIN\n"
        "  UPDATE t SET v = 'a;b' WHERE id = new.id;\n"
        "END;\n"
        "INSERT INTO t(id, v) VALUES (1, 'x;y');\n"
    )
    parts = _split_sql_statements(script)
    assert len(parts) == 3, parts
    assert "END;" in parts[1]


def test_exec_script_locked_does_not_drop_the_transaction(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute("BEGIN IMMEDIATE")
    _exec_script_locked(conn, "CREATE TABLE a (x INTEGER);\nCREATE TABLE b (y INTEGER);\n")
    assert conn.in_transaction
    conn.rollback()
    conn.close()


def test_migration_connection_swallows_commit_but_passes_through(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    guarded = _MigrationConnection(conn)
    conn.execute("BEGIN IMMEDIATE")
    guarded.execute("CREATE TABLE z (x INTEGER)")
    guarded.commit()
    guarded.rollback()
    assert conn.in_transaction, "commit()/rollback() must be inert during a migration"
    guarded.executescript("CREATE TABLE z2 (x INTEGER);")
    assert conn.in_transaction, "executescript() must not end the transaction"
    conn.rollback()
    conn.close()
