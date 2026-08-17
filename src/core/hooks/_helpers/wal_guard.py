"""
Force a WAL checkpoint when coding-os.db-wal has grown past its budget.

The connection-level `journal_size_limit` in thinking_os/_db_pool.py is the
real cap. This guard covers the one case that cap cannot reach: a checkpoint
blocked by a long-lived reader holding a snapshot, which is how the -wal
reached 59 GB beside a 342 MB database. When TRUNCATE comes back busy the
blocker is a process, not a setting, so the report names the PIDs instead of
saying "checkpoint failed" — that missing detail is what made the incident
expensive to diagnose.

Human report goes to stderr (the operator-visible channel); a one-line
machine summary goes to stdout for cos_log_hook. Always exits 0 — hygiene,
never a correctness gate.

USAGE
    python3 wal_guard.py <db_path> <threshold_bytes>
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys

_CHECKPOINT_BUSY_TIMEOUT_MS = 3000
_SUBPROCESS_TIMEOUT_SECONDS = 5
_MAX_COMMAND_CHARS = 110


def _format_bytes(count: int) -> str:
    step = 1024.0
    value = float(count)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(value) < step:
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= step
    return f"{value:.1f} PB"


def _size_or_zero(path: str) -> int:
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def _run(argv: list[str]) -> str:
    try:
        completed = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=_SUBPROCESS_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return completed.stdout


def _holder_pids(paths: list[str]) -> list[int]:
    # `lsof -t` prints bare PIDs. One call per path, not per candidate PID —
    # `paths` is 2 entries, so this stays two execs regardless of holder count.
    own_pid = os.getpid()
    pids: set[int] = set()
    for path in paths:
        for line in _run(["lsof", "-t", path]).split():
            try:
                pid = int(line)
            except ValueError:
                continue
            if pid != own_pid:
                pids.add(pid)
    return sorted(pids)


def _describe_holders(pids: list[int]) -> list[str]:
    if not pids:
        return []
    # `args` (not `cmd`/`comm`) is the POSIX spelling that yields the full
    # command line on both macOS and Linux.
    listing = _run(["ps", "-o", "pid=,etime=,args=", "-p", ",".join(str(p) for p in pids)])
    described = []
    for line in listing.splitlines():
        stripped = line.strip()
        if stripped:
            described.append(stripped[:_MAX_COMMAND_CHARS])
    return described or [f"pid {pid} (no ps entry)" for pid in pids]


def _checkpoint_truncate(db_path: str) -> tuple[int, int, int]:
    conn = sqlite3.connect(db_path, timeout=_CHECKPOINT_BUSY_TIMEOUT_MS / 1000.0)
    try:
        conn.execute(f"PRAGMA busy_timeout = {_CHECKPOINT_BUSY_TIMEOUT_MS}")
        row = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
    finally:
        conn.close()
    if row is None:
        return (1, 0, 0)
    return (int(row[0]), int(row[1]), int(row[2]))


def _report_blocked(wal_path: str, db_path: str, size_before: int) -> None:
    holders = _describe_holders(_holder_pids([wal_path, db_path]))
    print(
        f"[WARN] wal-guard: {_format_bytes(size_before)} WAL, checkpoint blocked (busy=1) "
        "— a reader is pinning the snapshot, retrying will not help.",
        file=sys.stderr,
    )
    if holders:
        print("       Holding the WAL open:", file=sys.stderr)
        for holder in holders:
            print(f"         {holder}", file=sys.stderr)
        print(
            "       Kill the stale process, then the next session start reclaims the space.",
            file=sys.stderr,
        )
    else:
        print(
            f"       No holder found (lsof unavailable?) — inspect manually: lsof -- {wal_path}",
            file=sys.stderr,
        )


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        return 0
    db_path, threshold_raw = argv[1], argv[2]
    try:
        threshold = int(threshold_raw)
    except ValueError:
        return 0

    wal_path = f"{db_path}-wal"
    size_before = _size_or_zero(wal_path)
    # Fast path: a stat call and nothing else. The guard runs at every session
    # start, so the healthy case must not open the database.
    if size_before <= threshold:
        return 0

    try:
        busy, _log_frames, _checkpointed = _checkpoint_truncate(db_path)
    except sqlite3.Error as exc:
        print(f"[FAIL] wal-guard: checkpoint raised {type(exc).__name__}: {exc}", file=sys.stderr)
        print(f"status=error wal_bytes={size_before}")
        return 0

    size_after = _size_or_zero(wal_path)
    reclaimed = size_before - size_after

    if busy:
        _report_blocked(wal_path, db_path, size_before)
        print(f"status=busy wal_bytes={size_before} reclaimed_bytes={reclaimed}")
        return 0

    print(
        f"[OK] wal-guard: reclaimed {_format_bytes(reclaimed)} "
        f"({_format_bytes(size_before)} → {_format_bytes(size_after)} WAL).",
        file=sys.stderr,
    )
    print(f"status=truncated wal_bytes={size_before} reclaimed_bytes={reclaimed}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
