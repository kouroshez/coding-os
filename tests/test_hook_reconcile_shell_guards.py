"""The shell reconcile hook starts one full reindex at a time.

A full `cos graph-reindex --force` holds the board DB write lock for minutes;
overlapping runs piled up and locked every board write. A fake `cos` on PATH
records each start, so no real reindex runs here.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[1] / "src" / "core" / "hooks"
HOOK = HOOKS / "auto-graph-reconcile-shell.sh"


@pytest.fixture()
def project(tmp_path: Path) -> Iterator[Path]:
    root = tmp_path / "proj"
    (root / ".coding-os").mkdir(parents=True)
    (root / "src").mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_cos = bin_dir / "cos"
    # Stays running until the test removes the blocker, so no assertion races it.
    blocker = tmp_path / "blocker"
    blocker.touch()
    fake_cos.write_text(
        f'#!/bin/sh\necho "$@" >> "{tmp_path}/cos-calls"\n'
        f'while [ -f "{blocker}" ]; do sleep 0.1; done\n'
    )
    fake_cos.chmod(0o755)
    yield root
    blocker.unlink(missing_ok=True)


def _fire(project: Path, command: str, shell: str = "bash") -> str:
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
    env.update(
        PATH=f"{project.parent / 'bin'}{os.pathsep}{os.environ['PATH']}",
        COS_STATE_DIR=str(project / ".coding-os"),
        COS_AGENT_DIR=str(project.parent / "agent"),
        COS_PANEL_DIR=str(project.parent / "agent" / "panel"),
        COS_PROJECT_ROOT=str(project),
        COS_HOOK_LOG=str(project.parent / "hooks.log"),
        COS_DB_PATH=str(project.parent / "unused.db"),
        COS_PYTHON="/usr/bin/true",  # the targeted path starts no real index worker
    )
    return subprocess.run(
        [shell, str(HOOK)],
        input=json.dumps({"tool_name": "Bash", "tool_input": {"command": command}}),
        env=env,
        cwd=str(project),
        capture_output=True,
        text=True,
        timeout=20,
        check=True,
    ).stdout


def _reindex_starts(project: Path, wait: float = 1.5) -> int:
    calls = project.parent / "cos-calls"
    deadline = time.monotonic() + wait
    while not calls.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    return calls.read_text().count("graph-reindex") if calls.exists() else 0


def test_a_bulk_delete_in_the_project_still_reconciles(project: Path) -> None:
    _fire(project, "rm -rf src/old")
    assert _reindex_starts(project) == 1


@pytest.mark.parametrize("shell", ["bash", "/bin/bash"])  # /bin/bash is 3.2 on macOS
def test_a_second_command_waits_for_the_reindex_the_hook_started(project: Path, shell: str) -> None:
    sentinel = project / ".coding-os" / ".reindex-scheduled"
    _fire(project, "rm -rf src/old", shell)
    assert _reindex_starts(project) == 1
    _age(sentinel, 120)  # past the 30 s grace, so only the live PID can debounce
    _fire(project, "rm -rf src/other", shell)
    time.sleep(0.5)
    assert _reindex_starts(project) == 1


def _dead_pid() -> int:
    child = subprocess.Popen(["true"])
    child.wait()
    return child.pid


def _age(path: Path, seconds: int) -> None:
    old = time.time() - seconds
    os.utime(path, (old, old))


def test_a_stale_sentinel_is_taken_over(project: Path) -> None:
    sentinel = project / ".coding-os" / ".reindex-scheduled"
    sentinel.write_text(str(_dead_pid()))
    _age(sentinel, 120)
    _fire(project, "rm -rf src/old")
    assert _reindex_starts(project) == 1


@pytest.mark.parametrize("shell", ["bash", "/bin/bash"])
def test_a_run_past_the_age_cap_keeps_its_claim(project: Path, shell: str) -> None:
    sentinel = project / ".coding-os" / ".reindex-scheduled"
    _fire(project, "rm -rf src/old", shell)
    assert _reindex_starts(project) == 1
    _age(sentinel, 1800)  # the hook's own job, still blocked in the fake cos
    _fire(project, "rm -rf src/other", shell)
    time.sleep(0.5)
    assert _reindex_starts(project) == 1


def test_a_run_past_two_hours_is_taken_over(project: Path) -> None:
    sentinel = project / ".coding-os" / ".reindex-scheduled"
    _fire(project, "rm -rf src/old")
    assert _reindex_starts(project) == 1
    _age(sentinel, 7300)
    _fire(project, "rm -rf src/other")
    deadline = time.monotonic() + 1.5
    while _reindex_starts(project, wait=0) < 2 and time.monotonic() < deadline:
        time.sleep(0.05)
    assert _reindex_starts(project, wait=0) == 2


def test_a_crashed_hooks_lock_is_cleared_without_a_takeover(project: Path) -> None:
    sentinel = project / ".coding-os" / ".reindex-scheduled"
    sentinel.write_text(str(_dead_pid()))
    _age(sentinel, 120)
    lock = project / ".coding-os" / ".reindex-scheduled.takeover"
    lock.mkdir()
    _age(lock, 120)
    _fire(project, "rm -rf src/old")
    assert not lock.exists()
    assert _reindex_starts(project, wait=1.0) == 0
    _fire(project, "rm -rf src/old")
    assert _reindex_starts(project) == 1


def test_a_takeover_backs_off_when_another_hook_took_it_first(project: Path) -> None:
    sentinel = project / ".coding-os" / ".reindex-scheduled"
    sentinel.write_text(str(_dead_pid()))
    _age(sentinel, 120)
    # Simulates hook A finishing its takeover between this hook's stale check
    # and its lock: the sentinel changes just before the lock is taken.
    fake_mkdir = project.parent / "bin" / "mkdir"
    fake_mkdir.write_text(
        '#!/bin/sh\ncase "$1" in *.takeover) printf 4242 > "' + str(sentinel) + '";; esac\n'
        'exec /bin/mkdir "$@"\n'
    )
    fake_mkdir.chmod(0o755)
    _fire(project, "rm -rf src/old")
    assert _reindex_starts(project, wait=1.0) == 0
    assert sentinel.read_text() == "4242"


def test_removing_one_file_reconciles_only_that_path(project: Path) -> None:
    out = _fire(project, "rm src/a.py")
    assert "reconcile 1 paths" in out
    assert _reindex_starts(project, wait=1.0) == 0


def test_a_sentinel_dated_in_the_future_is_taken_over(project: Path) -> None:
    sentinel = project / ".coding-os" / ".reindex-scheduled"
    sentinel.write_text(str(_dead_pid()))
    _age(sentinel, -3600)  # the clock stepped back
    _fire(project, "rm -rf src/old")
    assert _reindex_starts(project) == 1


def test_a_symlinked_sentinel_cannot_defeat_single_flight(project: Path) -> None:
    sentinel = project / ".coding-os" / ".reindex-scheduled"
    sentinel.symlink_to("/dev/zero")  # e.g. committed into a cloned repo
    _fire(project, "rm -rf src/old")
    assert _reindex_starts(project) == 1
    assert sentinel.is_file() and not sentinel.is_symlink()
    _fire(project, "rm -rf src/other")
    time.sleep(0.5)
    assert _reindex_starts(project) == 1


def test_a_directory_at_the_sentinel_path_is_replaced(project: Path) -> None:
    sentinel = project / ".coding-os" / ".reindex-scheduled"
    (sentinel / "planted").mkdir(parents=True)  # e.g. tracked in a cloned repo
    _fire(project, "rm -rf src/old")
    assert _reindex_starts(project) == 1
    assert sentinel.is_file()


def test_a_planted_temp_name_is_never_written_through(project: Path) -> None:
    state = project / ".coding-os"
    victim = project.parent / "victim"
    victim.write_text("keep me")
    # The next PIDs handed out, so the old predictable name would hit a plant.
    first = _dead_pid() + 1
    for pid in range(first, first + 3000):
        (state / f".reindex-scheduled.{pid}").symlink_to(victim)
    _fire(project, "rm -rf src/old")
    assert _reindex_starts(project) == 1
    sentinel = state / ".reindex-scheduled"
    assert sentinel.is_file() and not sentinel.is_symlink()
    assert sentinel.read_text().isdigit()
    assert victim.read_text() == "keep me"
