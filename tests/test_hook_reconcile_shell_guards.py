"""The shell reconcile hook starts one full reindex at a time, and none for scratch work.

A full `cos graph-reindex --force` holds the board DB write lock for minutes;
overlapping runs and runs fired by commands in a scratch clone piled up and
locked every board write (TASK-1126). A fake `cos` on PATH records each start
so no real reindex runs here.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

import pytest

HOOK = (
    Path(__file__).resolve().parents[1] / "src" / "core" / "hooks" / "auto-graph-reconcile-shell.sh"
)


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    (root / ".coding-os").mkdir(parents=True)
    (root / "src").mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_cos = bin_dir / "cos"
    fake_cos.write_text(f'#!/bin/sh\necho "$@" >> "{tmp_path}/cos-calls"\n')
    fake_cos.chmod(0o755)
    return root


def _fire(project: Path, command: str) -> None:
    payload = {"tool_name": "Bash", "tool_input": {"command": command}}
    env = {
        **os.environ,
        "PATH": f"{project.parent / 'bin'}{os.pathsep}{os.environ['PATH']}",
        "COS_STATE_DIR": str(project / ".coding-os"),
        "COS_PROJECT_ROOT": str(project),
    }
    subprocess.run(
        ["bash", str(HOOK)],
        input=json.dumps(payload),
        env=env,
        cwd=project,
        capture_output=True,
        text=True,
        timeout=20,
        check=True,
    )


def _reindex_starts(project: Path) -> int:
    calls = project.parent / "cos-calls"
    deadline = time.monotonic() + 3
    while not calls.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    return calls.read_text().count("graph-reindex") if calls.exists() else 0


def test_a_bulk_delete_in_the_project_still_reconciles(project: Path) -> None:
    _fire(project, "rm -rf src/old")
    assert _reindex_starts(project) == 1


def test_a_command_in_a_scratch_clone_starts_nothing(project: Path) -> None:
    _fire(project, 'cd "$S/clone" && rm -rf src/old && cp tests/a.py src/')
    _fire(project, "rm -rf /private/tmp/scratch/clone/src/old")
    assert _reindex_starts(project) == 0


def test_no_second_reindex_while_one_is_running(project: Path) -> None:
    sentinel = project / ".coding-os" / ".reindex-scheduled"
    sentinel.write_text(str(os.getpid()))
    old = time.time() - 120
    os.utime(sentinel, (old, old))
    _fire(project, "rm -rf src/old")
    assert _reindex_starts(project) == 0
