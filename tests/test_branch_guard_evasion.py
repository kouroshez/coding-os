"""Behavior tests for branch-guard.sh — trunk-based workflow enforcement (TASK-012)."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

HOOK = Path(__file__).resolve().parent.parent / "src" / "core" / "hooks" / "branch-guard.sh"


def _run(
    command: str,
    *,
    tool: str = "Bash",
    workflow: str | None = None,
    extra_env: dict[str, str] | None = None,
) -> tuple[int, str]:
    # strip both so an inherited COS_WORKTREE_ROOT can't flip the per-op scope tests
    _drop = {
        "COS_GIT_WORKFLOW",
        "COS_WORKTREE_ROOT",
        "COS_GIT_PROTECTED_BRANCHES",
        "COS_GIT_INTEGRATION_BRANCH",
    }
    env = {k: v for k, v in os.environ.items() if k not in _drop}
    if workflow is not None:
        env["COS_GIT_WORKFLOW"] = workflow
    if extra_env:
        env.update(extra_env)
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


_WT = "/tmp/repo/.coding-os/worktrees/slug/task-1"


def test_blocks_reset_with_double_space() -> None:
    code, _ = _run("git  reset HEAD~1")
    assert code == 2


def test_blocks_reset_with_tab() -> None:
    code, _ = _run("git\treset HEAD~1")
    assert code == 2


def test_blocks_reset_via_git_dash_C() -> None:
    code, _ = _run("git -C /tmp reset HEAD~1")
    assert code == 2


def test_blocks_reset_via_git_dash_c_config() -> None:
    code, _ = _run("git -c core.editor=vi reset HEAD~1")
    assert code == 2


def test_blocks_reset_via_git_dir_long_opt() -> None:
    code, _ = _run("git --git-dir=.git reset HEAD~1")
    assert code == 2


def test_blocks_reset_nested_sh_dash_c() -> None:
    code, _ = _run('sh -c "git reset HEAD~1"')
    assert code == 2


def test_blocks_reset_nested_bash_dash_c_single_quote() -> None:
    code, _ = _run("bash -c 'git reset HEAD~1'")
    assert code == 2


def test_blocks_checkout_nested_in_sh_c() -> None:
    code, _ = _run("sh -c 'git checkout feature-x'")
    assert code == 2


def test_blocks_with_leading_env_var() -> None:
    code, _ = _run("FOO=bar git reset HEAD~1")
    assert code == 2


def test_allows_literal_string_in_echo() -> None:
    code, _ = _run("echo 'do not run git reset HEAD~1'")
    assert code == 0


def test_allows_literal_string_in_grep() -> None:
    code, _ = _run("grep 'git reset HEAD~1' docs/")
    assert code == 0


def test_blocks_doubly_nested_sh_c() -> None:
    code, _ = _run("sh -c \"sh -c 'git reset HEAD~1'\"")
    assert code == 2


def test_blocks_backtick_nested_in_echo() -> None:
    # `echo `git reset HEAD~1`` — backtick body must be inspected even
    # when the outer command name is `echo`.
    code, _ = _run("echo `git reset HEAD~1`")
    assert code == 2


def test_blocks_multi_level_nested_shells() -> None:
    code, _ = _run('bash -c "sh -c \\"git checkout feature-x\\""')
    assert code == 2


def test_blocks_rebase_via_git_dash_C() -> None:
    code, _ = _run("git -C /tmp rebase main")
    assert code == 2


def test_blocks_rebase_in_nested_sh_c() -> None:
    code, _ = _run("sh -c 'git rebase -i HEAD~3'")
    assert code == 2
