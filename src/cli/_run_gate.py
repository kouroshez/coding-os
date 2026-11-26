"""The test governor `cos run` applies itself: sweep gate, dedup, one-heavy-run lock, ledger.

A hook that matches Bash text never sees what `cos run test-backend` executes,
so the gate lives in the runner. Spec: docs/engineering/test-governance.md § cos run.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import NoReturn

import click

_HOOKS_DIR = Path(__file__).resolve().parent.parent / "core" / "hooks"
_LOCK_TTL_SECONDS = 1800
_MIN_OVERRIDE_REASON_CHARS = 15


def run_governed(name: str, shell: str, root: Path) -> int:
    from board_os.verify_suites_cli import match_command

    state = root / os.environ.get("COS_STATE_DIR", ".coding-os")
    os.environ["COS_PROJECT_ROOT"] = str(root)
    os.environ["COS_STATE_DIR"] = str(state)
    verify_file = state / ".last-verify.json"
    as_suite = match_command(f"cos run {name}", verify_file)
    as_shell = match_command(shell, verify_file)
    suite = as_suite["suite"]
    if not suite and not as_shell["pytest_invocation"]:
        return subprocess.run(shell, shell=True, cwd=root).returncode
    if not suite and as_shell["full_sweep"]:
        _require_sweep_override()
    if suite and as_suite["fresh"] and os.environ.get("COS_TEST_FORCE") != "1":
        _refuse(
            f"{suite} is already green on this exact tree — passed "
            f"{as_suite.get('age_min', 0)}min ago by {as_suite.get('recorded_by', 'unknown')}.\n"
            "  Reuse that result; it goes stale when the tree changes.\n"
            f"  Re-run anyway: COS_TEST_FORCE=1 cos run {name}"
        )
    lock = state / ".test-run.lock"
    _take_lock(lock, suite)
    try:
        code = subprocess.run(shell, shell=True, cwd=root).returncode
    finally:
        _release_lock(lock)
    if suite:
        status = "PASS" if code == 0 else "FAIL"
        recorded = subprocess.run(
            ["bash", str(_HOOKS_DIR / "record-verify.sh"), suite, status],
            cwd=root,
            stdout=subprocess.DEVNULL,
            check=False,
        )
        if recorded.returncode != 0:
            click.echo(f"[WARN] {suite} {status} was not written to {verify_file}", err=True)
    return code


def _refuse(message: str) -> NoReturn:
    click.echo(f"BLOCKED: {message}", err=True)
    sys.exit(2)


def _require_sweep_override() -> None:
    reason = os.environ.get("COS_OVERRIDE_REASON", "")
    if os.environ.get("COS_FULL_SWEEP_OK") == "1" and len(reason) >= _MIN_OVERRIDE_REASON_CHARS:
        subprocess.run(
            [
                "bash",
                "-c",
                'source "$1/cos-env.sh" && cos_log_hook cos-run override "full-sweep reason=$2"',
                "cos-run",
                str(_HOOKS_DIR),
                reason,
            ],
            capture_output=True,
            check=False,
        )
        return
    _refuse(
        "full pytest sweep mid-task (Rule 20).\n"
        "  Run the suite for what you changed instead.\n"
        "  Pre-merge or asked for? COS_FULL_SWEEP_OK=1 COS_OVERRIDE_REASON='...>=15 chars' cos run ..."
    )


def _take_lock(lock: Path, suite: str | None) -> None:
    tail = os.environ.get("COS_PANEL_ID", "")[-8:]
    now = int(time.time())
    lock.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(2):
        try:
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            if attempt:
                _refuse("another test run took the lock a moment ago; retry after it finishes.")
            _refuse_if_held(lock, tail, now)
            lock.unlink(missing_ok=True)
            continue
        entry = {
            "suite": suite or "adhoc-pytest",
            "agent": os.environ.get("COS_AGENT", "unknown"),
            "session_tail": tail,
            "agent_pid": os.getpid(),
            "started_ts": now,
        }
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(entry, handle)
        return


def _refuse_if_held(lock: Path, tail: str, now: int) -> None:
    try:
        holder = json.loads(lock.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    started = holder.get("started_ts")
    age = now - started if isinstance(started, int) else _LOCK_TTL_SECONDS
    ours = bool(tail) and holder.get("session_tail") == tail
    if age < _LOCK_TTL_SECONDS and _alive(holder.get("agent_pid")) and not ours:
        _refuse(
            f"{holder.get('agent', 'unknown')} is running {holder.get('suite', 'a test run')} "
            f"on this machine (started {age}s ago).\n"
            f"  Retry after it finishes; the lock clears itself or expires after {_LOCK_TTL_SECONDS}s."
        )


def _release_lock(lock: Path) -> None:
    try:
        holder = json.loads(lock.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if holder.get("agent_pid") == os.getpid():
        lock.unlink(missing_ok=True)


def _alive(pid: object) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True
