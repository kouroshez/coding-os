"""The shell reconcile hook starts one full reindex at a time, and none for provable scratch work.

A full `cos graph-reindex --force` holds the board DB write lock for minutes;
overlapping runs, and runs fired by commands in a scratch clone, piled up and
locked every board write. Skipping a command that did change the project is
worse: the graph then answers wrongly. A fake `cos` on PATH records each start
so no real reindex runs here.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[1] / "src" / "core" / "hooks"
HOOK = HOOKS / "auto-graph-reconcile-shell.sh"
sys.path.insert(0, str(HOOKS / "_helpers"))

from reconcile_scope import decide

ROOT = "/work/proj"


@pytest.mark.parametrize(
    "command",
    [
        "rm -rf src/old",
        "cp /tmp/clone/tests/golden/a.json tests/golden/a.json",
        "git rm src/x.py > /dev/null",
        "rm -rf src/old && echo ok >> /tmp/log",
        "mv src/a.py src/b.py 2>&1 | tee /tmp/out",
        "cd src/core && git rm old.py",
        f"cd {ROOT} && rm -rf src/old",
        f"rm {ROOT}/docs/x.md",
        'cd "$S/clone" && rm -rf src/old',
        "cd $CLAUDE_PROJECT_DIR && rm src/a.py",
    ],
)
def test_a_command_that_may_touch_the_project_reconciles(command: str) -> None:
    assert decide(command, ROOT) == "go"


@pytest.mark.parametrize(
    "command",
    [
        "cd /private/tmp/scratch/clone && rm -rf src/old && cp tests/a.py src/",
        "rm -rf /private/tmp/scratch/clone/src/old",
        f"rm -rf {ROOT}-scratch/src/old",
    ],
)
def test_a_command_provably_outside_the_project_is_skipped(command: str) -> None:
    assert decide(command, ROOT) == "skip"


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    (root / ".coding-os").mkdir(parents=True)
    (root / "src").mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_cos = bin_dir / "cos"
    fake_cos.write_text(f'#!/bin/sh\necho "$@" >> "{tmp_path}/cos-calls"\nsleep 2\n')
    fake_cos.chmod(0o755)
    return root


def _fire(project: Path, command: str, **env_overrides: str) -> None:
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
    env.update(
        PATH=f"{project.parent / 'bin'}{os.pathsep}{os.environ['PATH']}",
        COS_STATE_DIR=str(project / ".coding-os"),
        COS_AGENT_DIR=str(project.parent / "agent"),
        COS_PANEL_DIR=str(project.parent / "agent" / "panel"),
        COS_PROJECT_ROOT=str(project),
    )
    env.update(env_overrides)
    subprocess.run(
        ["bash", str(HOOK)],
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


def test_a_literal_scratch_clone_command_starts_nothing(project: Path) -> None:
    _fire(project, "cd /private/tmp/scratch/clone && rm -rf src/old")
    assert _reindex_starts(project) == 0


def test_a_second_command_waits_for_the_reindex_the_hook_started(project: Path) -> None:
    sentinel = project / ".coding-os" / ".reindex-scheduled"
    _fire(project, "rm -rf src/old")
    assert _reindex_starts(project) == 1
    old = time.time() - 120  # past the 30 s grace, so only the live PID can debounce
    os.utime(sentinel, (old, old))
    _fire(project, "rm -rf src/other")
    time.sleep(0.5)
    assert _reindex_starts(project) == 1


def test_the_root_comes_from_claude_project_dir_when_cwd_is_elsewhere(project: Path) -> None:
    _fire(
        project,
        f"rm -rf {project}/src/old",
        COS_PROJECT_ROOT="",
        CLAUDE_PROJECT_DIR=str(project),
        _CWD=str(project / "src"),
    )
    assert _reindex_starts(project) == 1
