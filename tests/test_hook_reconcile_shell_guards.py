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


def _fire(project: Path, command: str, shell: str = "bash", **env_overrides: str) -> None:
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
    env.update(
        PATH=f"{project.parent / 'bin'}{os.pathsep}{os.environ['PATH']}",
        COS_STATE_DIR=str(project / ".coding-os"),
        COS_AGENT_DIR=str(project.parent / "agent"),
        COS_PANEL_DIR=str(project.parent / "agent" / "panel"),
        COS_PROJECT_ROOT=str(project),
        COS_HOOK_LOG=str(project.parent / "hooks.log"),
        COS_DB_PATH=str(project.parent / "unused.db"),
    )
    env.update(env_overrides)
    subprocess.run(
        [shell, str(HOOK)],
        input=json.dumps({"tool_name": "Bash", "tool_input": {"command": command}}),
        env=env,
        cwd=env_overrides.get("_CWD", str(project)),
        capture_output=True,
        text=True,
        timeout=20,
        check=True,
    )


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
    old = time.time() - 120  # past the 30 s grace, so only the live PID can debounce
    os.utime(sentinel, (old, old))
    _fire(project, "rm -rf src/other", shell)
    time.sleep(0.5)
    assert _reindex_starts(project) == 1


def test_a_stale_sentinel_is_taken_over(project: Path) -> None:
    sentinel = project / ".coding-os" / ".reindex-scheduled"
    sentinel.write_text("999999")  # no such process
    old = time.time() - 120
    os.utime(sentinel, (old, old))
    _fire(project, "rm -rf src/old")
    assert _reindex_starts(project) == 1
