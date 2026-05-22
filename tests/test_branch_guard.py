"""Behavior tests for branch-guard.sh — trunk-based workflow enforcement (TASK-012)."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

HOOK = Path(__file__).resolve().parent.parent / "src" / "core" / "hooks" / "branch-guard.sh"


def _run(command: str, *, tool: str = "Bash", workflow: str | None = None) -> tuple[int, str]:
    env = {k: v for k, v in os.environ.items() if k != "COS_GIT_WORKFLOW"}
    if workflow is not None:
        env["COS_GIT_WORKFLOW"] = workflow
    proc = subprocess.run(
        ["bash", str(HOOK)],
        input=json.dumps({"tool_name": tool, "tool_input": {"command": command}}),
        capture_output=True,
        text=True,
        timeout=5,
        env=env,
    )
    return proc.returncode, proc.stderr


# --- blocked: branch / worktree creation in trunk mode --------------------


def test_blocks_checkout_dash_b() -> None:
    code, err = _run("git checkout -b feature/foo")
    assert code == 2
    assert "trunk-based" in err


def test_blocks_switch_dash_c() -> None:
    code, _ = _run("git switch -c feature/foo")
    assert code == 2


def test_blocks_branch_create() -> None:
    code, _ = _run("git branch newfeature")
    assert code == 2


def test_blocks_worktree_add() -> None:
    code, _ = _run("git worktree add ../wt-foo")
    assert code == 2


def test_blocks_compound_command() -> None:
    code, _ = _run("cd src && git checkout -b feature/foo")
    assert code == 2


# --- allowed: operations on existing branches -----------------------------


def test_allows_branch_list() -> None:
    code, _ = _run("git branch")
    assert code == 0


def test_allows_branch_delete() -> None:
    code, _ = _run("git branch -d oldbranch")
    assert code == 0


def test_allows_checkout_existing() -> None:
    code, _ = _run("git checkout main")
    assert code == 0


def test_allows_commit_with_paths() -> None:
    code, _ = _run("git commit foo.py -m 'fix'")
    assert code == 0


def test_allows_non_bash_tool() -> None:
    code, _ = _run("git checkout -b foo", tool="Edit")
    assert code == 0


# --- pr mode: branches permitted (the future-team seam) -------------------


def test_pr_mode_allows_branch_create() -> None:
    code, _ = _run("git checkout -b feature/foo", workflow="pr")
    assert code == 0
