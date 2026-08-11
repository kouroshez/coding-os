"""Behavior tests for branch-guard.sh — trunk-based workflow enforcement (TASK-012)."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

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


def test_allows_bare_reset() -> None:
    code, _ = _run("git reset")
    assert code == 0


def test_allows_reset_mixed_head() -> None:
    code, _ = _run("git reset --mixed HEAD")
    assert code == 0


def test_allows_reset_path() -> None:
    # `git reset -- foo.py` unstages one path; HEAD does not move.
    code, _ = _run("git reset -- foo.py")
    assert code == 0


@pytest.mark.parametrize(
    "command",
    [
        "git reset -p",  # interactive patch — false-blocked before
        "git reset --patch",  # long form
        "git reset --pat",  # --patch abbrev
        "git reset --pathspec-from-file f",  # explicit path-mode
        "git reset --soft HEAD",  # mode + HEAD = no move
        "git reset --har HEAD",  # abbrev mode + HEAD = still no move
    ],
)
def test_allows_reset_path_mode_and_head(command: str) -> None:
    code, _ = _run(command)
    assert code == 0


def test_allows_checkout_main() -> None:
    code, _ = _run("git checkout main")
    assert code == 0


def test_allows_checkout_file_restore() -> None:
    code, _ = _run("git checkout -- src/foo.py")
    assert code == 0


def test_allows_checkout_file_from_head() -> None:
    # `git checkout HEAD <path>` restores from HEAD; HEAD stays.
    code, _ = _run("git checkout HEAD src/foo.py")
    assert code == 0


def test_allows_checkout_file_from_sha() -> None:
    code, _ = _run("git checkout abc1234 -- src/foo.py")
    assert code == 0


def test_allows_switch_main() -> None:
    code, _ = _run("git switch main")
    assert code == 0


def test_allows_revert() -> None:
    # revert is the trunk-based way to undo a commit.
    code, _ = _run("git revert HEAD")
    assert code == 0


def test_allows_checkout_dot_for_restore_cwd() -> None:
    # `git checkout .` restores all files in cwd — HEAD does not move.
    code, _ = _run("git checkout .")
    assert code == 0


def test_allows_git_log_grep_with_literal() -> None:
    # `git log --grep='...'` is read-only; the literal inside should not block.
    code, _ = _run("git log --grep='git reset HEAD~1'")
    assert code == 0


def test_allows_git_status_alongside_literal_text() -> None:
    code, _ = _run("git status # noted: do not run git reset HEAD~1")
    assert code == 0


def test_allows_git_show_other_branch() -> None:
    # `git show <branch>:path` reads from another ref but doesn't move HEAD.
    code, _ = _run("git show feature-x:src/foo.py")
    assert code == 0


def test_allows_git_diff_two_refs() -> None:
    code, _ = _run("git diff main..HEAD")
    assert code == 0


def test_allows_escaped_backticks_in_commit_message() -> None:
    # `\`git reset HEAD~1\`` inside a `git commit -m` arg is an inert
    # literal — bash does not execute escaped backticks. Must NOT block.
    code, _ = _run("git commit -m 'see \\`git reset HEAD~1\\` for the unsafe form' foo.py")
    assert code == 0


def test_allows_rebase_abort() -> None:
    code, _ = _run("git rebase --abort")
    assert code == 0


def test_allows_rebase_continue() -> None:
    code, _ = _run("git rebase --continue")
    assert code == 0


def test_allows_rebase_skip() -> None:
    code, _ = _run("git rebase --skip")
    assert code == 0


def test_allows_rebase_quit() -> None:
    code, _ = _run("git rebase --quit")
    assert code == 0


def test_allows_rebase_show_current_patch() -> None:
    code, _ = _run("git rebase --show-current-patch")
    assert code == 0


def test_allows_pull_rebase_origin_main() -> None:
    # `git pull --rebase origin main` is the documented trunk integration
    # step — subcommand is `pull`, not `rebase`. Must NOT block.
    code, _ = _run("git pull --rebase origin main")
    assert code == 0
