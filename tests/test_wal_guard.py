"""wal_guard + journal_size_limit — the two mechanisms bounding coding-os.db-wal.

Guards the incident where the -wal reached 59 GB beside a 342 MB database while
holding only 531 live frames: the file was a never-truncated high-water mark
(`journal_size_limit = -1`) that no checkpoint could give back, because stale
readers pinned the snapshot (TASK-1008).
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_GUARD = _ROOT / "src" / "core" / "hooks" / "_helpers" / "wal_guard.py"
sys.path.insert(0, str(_ROOT / "src" / "core"))

from thinking_os._db_pool import WAL_SIZE_LIMIT_BYTES, apply_pragmas

_OVER_CAP_BYTES = WAL_SIZE_LIMIT_BYTES + 8 * 1024 * 1024
_SMALL_WAL_BYTES = 12 * 1024 * 1024
_SMALL_THRESHOLD_BYTES = 8 * 1024 * 1024


def _fill_wal(db_path: str, target_bytes: int) -> sqlite3.Connection:
    """Grow the -wal past target and return the STILL-OPEN connection.

    Closing the last connection checkpoints and deletes the -wal, which would
    erase the condition under test — and is itself why reproducing the incident
    needs a long-lived server process.
    """
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA wal_autocheckpoint = 0")
    conn.execute("PRAGMA journal_size_limit = -1")
    conn.execute("CREATE TABLE IF NOT EXISTS blob_rows (id INTEGER PRIMARY KEY, payload BLOB)")
    conn.commit()
    payload = os.urandom(64 * 1024)
    while os.path.getsize(f"{db_path}-wal") < target_bytes:
        conn.execute("INSERT INTO blob_rows (payload) VALUES (?)", (payload,))
        conn.commit()
    return conn


def _run_guard(db_path: str, threshold: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_GUARD), db_path, str(threshold)],
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_apply_pragmas_sets_the_wal_cap() -> None:
    conn = sqlite3.connect(":memory:")
    apply_pragmas(conn)
    assert conn.execute("PRAGMA journal_size_limit").fetchone()[0] == WAL_SIZE_LIMIT_BYTES
    conn.close()


def test_cap_is_below_the_doctor_wal_budget() -> None:
    # cos doctor warns at 50 MB (_doctor_runtime.WRITE_AHEAD_LOG_BUDGET_MEGABYTES).
    # A cap at or above it would make a healthy WAL trip that check forever.
    assert WAL_SIZE_LIMIT_BYTES < 50 * 1024 * 1024


@pytest.mark.slow
def test_over_cap_wal_shrinks_at_the_next_wal_restart(tmp_path: Path) -> None:
    db = str(tmp_path / "cap.db")
    filler = _fill_wal(db, _OVER_CAP_BYTES)
    try:
        grown = os.path.getsize(f"{db}-wal")
        assert grown > WAL_SIZE_LIMIT_BYTES

        capped = sqlite3.connect(db)
        apply_pragmas(capped)
        capped.execute("PRAGMA wal_checkpoint(RESTART)")

        # Measured on SQLite 3.50.4: the limit lands at the WAL *restart* (the
        # log wrapping to frame 0 on the next write), not at checkpoint
        # completion. Asserting both moments stops a future reader from
        # concluding the pragma is ignored and "fixing" a non-bug.
        assert os.path.getsize(f"{db}-wal") >= grown

        capped.execute("CREATE TABLE IF NOT EXISTS ping (x INTEGER)")
        capped.execute("INSERT INTO ping (x) VALUES (1)")
        capped.commit()
        capped.close()

        assert os.path.getsize(f"{db}-wal") <= WAL_SIZE_LIMIT_BYTES
    finally:
        filler.close()


def test_guard_is_silent_and_opens_nothing_below_threshold(tmp_path: Path) -> None:
    db = str(tmp_path / "small.db")
    filler = _fill_wal(db, 1 * 1024 * 1024)
    try:
        proc = _run_guard(db, 50 * 1024 * 1024)
        assert proc.returncode == 0
        assert proc.stdout == ""
        assert proc.stderr == ""
    finally:
        filler.close()


def test_guard_truncates_and_reports_reclaimed_bytes(tmp_path: Path) -> None:
    db = str(tmp_path / "big.db")
    filler = _fill_wal(db, _SMALL_WAL_BYTES)
    try:
        before = os.path.getsize(f"{db}-wal")
        proc = _run_guard(db, _SMALL_THRESHOLD_BYTES)
        after = os.path.getsize(f"{db}-wal")

        assert proc.returncode == 0
        assert after < before
        assert "[OK]" in proc.stderr
        assert "reclaimed" in proc.stderr
        assert "status=truncated" in proc.stdout
        assert f"reclaimed_bytes={before - after}" in proc.stdout
    finally:
        filler.close()


def test_guard_names_the_pid_blocking_the_checkpoint(tmp_path: Path) -> None:
    db = str(tmp_path / "busy.db")
    filler = _fill_wal(db, _SMALL_WAL_BYTES)
    reader_source = textwrap.dedent(f"""
        import sqlite3, time
        conn = sqlite3.connect({db!r})
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("BEGIN")
        conn.execute("SELECT count(*) FROM blob_rows").fetchone()
        print("ready", flush=True)
        time.sleep(60)
    """)
    reader = subprocess.Popen(
        [sys.executable, "-c", reader_source], stdout=subprocess.PIPE, text=True
    )
    try:
        assert reader.stdout is not None
        reader.stdout.readline()  # blocks until the read transaction is open
        time.sleep(0.3)

        proc = _run_guard(db, _SMALL_THRESHOLD_BYTES)

        # A blocked checkpoint is a process problem, not a retry problem — the
        # PID is the whole diagnostic, and its absence is what made the
        # original incident expensive.
        assert proc.returncode == 0
        assert "[WARN]" in proc.stderr
        assert "busy=1" in proc.stderr
        assert str(reader.pid) in proc.stderr
        assert "status=busy" in proc.stdout
    finally:
        reader.kill()
        reader.wait()
        filler.close()


def test_guard_tolerates_a_missing_wal(tmp_path: Path) -> None:
    db = str(tmp_path / "absent.db")
    sqlite3.connect(db).close()
    proc = _run_guard(db, _SMALL_THRESHOLD_BYTES)
    assert proc.returncode == 0
    assert proc.stderr == ""


def test_guard_tolerates_bad_arguments(tmp_path: Path) -> None:
    db = str(tmp_path / "args.db")
    sqlite3.connect(db).close()
    assert _run_guard(db, 0).returncode == 0
    bad = subprocess.run(
        [sys.executable, str(_GUARD), db, "not-a-number"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert bad.returncode == 0


def _recovery_step(tmp_path: Path, wal_bytes: int, free_bytes: int, monkeypatch) -> str:
    sys.path.insert(0, str(_ROOT / "src"))
    from cli import _doctor_runtime

    wal = tmp_path / "coding-os.db-wal"
    wal.write_bytes(b"")
    monkeypatch.setattr(
        _doctor_runtime.shutil,
        "disk_usage",
        lambda _p: SimpleNamespace(free=free_bytes),
    )
    return _doctor_runtime._wal_recovery_step(wal, wal_bytes)


def test_recovery_step_recommends_truncate_when_the_volume_has_room(tmp_path, monkeypatch) -> None:
    step = _recovery_step(
        tmp_path, wal_bytes=60 * 1024**3, free_bytes=200 * 1024**3, monkeypatch=monkeypatch
    )
    assert "wal_checkpoint(TRUNCATE)" in step
    assert "do NOT" not in step


def test_recovery_step_refuses_truncate_when_free_space_is_under_the_wal(
    tmp_path, monkeypatch
) -> None:
    """The incident volume had 32 GB free beside a 59 GB WAL.

    A recovery step that folds the whole WAL into the DB in one pass is the
    wrong advice there, and 'it failed halfway' is the worst way to learn it.
    """
    step = _recovery_step(
        tmp_path, wal_bytes=59 * 1024**3, free_bytes=32 * 1024**3, monkeypatch=monkeypatch
    )
    assert "do NOT run wal_checkpoint(TRUNCATE)" in step
    assert "PASSIVE" in step
    assert "32768 MB free" in step or "32768 MB" in step


def test_recovery_step_falls_back_to_truncate_when_free_space_is_unreadable(
    tmp_path, monkeypatch
) -> None:
    sys.path.insert(0, str(_ROOT / "src"))
    from cli import _doctor_runtime

    def _boom(_p):
        raise OSError("statvfs unavailable")

    monkeypatch.setattr(_doctor_runtime.shutil, "disk_usage", _boom)
    step = _doctor_runtime._wal_recovery_step(tmp_path / "coding-os.db-wal", 1024)
    assert "wal_checkpoint(TRUNCATE)" in step


def test_db_finding_reports_what_a_vacuum_would_return(tmp_path, monkeypatch) -> None:
    """An over-budget DB is not necessarily a full one.

    Free pages are space SQLite reuses but never hands back, and nothing in
    the product returns them — VACUUM exists but no scheduled leg calls it
    (TASK-1045). Measured here at 326 MB: 2,137 free pages, ~9 MB. Reporting
    that separates "run one command" from "go prune the graph".
    """
    import sqlite3
    import sys

    sys.path.insert(0, str(_ROOT / "src"))
    from cli import _doctor_runtime

    db = tmp_path / "coding-os.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE blob_rows (id INTEGER PRIMARY KEY, payload BLOB)")
    conn.executemany(
        "INSERT INTO blob_rows (payload) VALUES (?)", [(os.urandom(4096),) for _ in range(400)]
    )
    conn.commit()
    conn.execute("DELETE FROM blob_rows")
    conn.commit()
    conn.close()

    reclaimable = _doctor_runtime._reclaimable_megabytes(db)
    assert reclaimable is not None and reclaimable > 0, "deleted rows left no free pages to report"


def test_reclaimable_is_none_when_the_db_cannot_be_read(tmp_path) -> None:
    import sys

    sys.path.insert(0, str(_ROOT / "src"))
    from cli import _doctor_runtime

    assert _doctor_runtime._reclaimable_megabytes(tmp_path / "absent.db") is None
