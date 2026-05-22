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


# --- blocked: HEAD-rewriting ops (TASK-013) -------------------------------


def test_blocks_reset_head_tilde() -> None:
    code, err = _run("git reset HEAD~1")
    assert code == 2
    assert "reset" in err.lower()


def test_blocks_reset_soft_head_tilde() -> None:
    code, _ = _run("git reset --soft HEAD~2")
    assert code == 2


def test_blocks_reset_to_sha() -> None:
    code, _ = _run("git reset abc1234")
    assert code == 2


def test_blocks_reset_to_remote_ref() -> None:
    code, _ = _run("git reset origin/main")
    assert code == 2


def test_blocks_checkout_other_branch() -> None:
    code, err = _run("git checkout feature-x")
    assert code == 2
    assert "checkout" in err.lower() or "trunk" in err.lower()


def test_blocks_switch_other_branch() -> None:
    code, _ = _run("git switch feature-x")
    assert code == 2


def test_blocks_switch_previous_branch() -> None:
    code, _ = _run("git switch -")
    assert code == 2


def test_blocks_checkout_detached_head_via_ref() -> None:
    # `git checkout HEAD~1` without a path arg detaches HEAD — unsafe.
    code, _ = _run("git checkout HEAD~1")
    assert code == 2


# --- allowed: safe HEAD-stable forms --------------------------------------


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


# --- pr mode: branches + HEAD-moves permitted (future-team seam) ----------


def test_pr_mode_allows_branch_create() -> None:
    code, _ = _run("git checkout -b feature/foo", workflow="pr")
    assert code == 0


def test_pr_mode_allows_reset_head_tilde() -> None:
    code, _ = _run("git reset HEAD~1", workflow="pr")
    assert code == 0


# --- TASK-014 hardening: bypass probes (must BLOCK after this task) -------


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
    code, _ = _run("sh -c \"git reset HEAD~1\"")
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


# --- TASK-014 hardening: false-positive probes (must ALLOW after this task)


def test_allows_checkout_dot_for_restore_cwd() -> None:
    # `git checkout .` restores all files in cwd — HEAD does not move.
    code, _ = _run("git checkout .")
    assert code == 0


def test_allows_literal_string_in_echo() -> None:
    code, _ = _run("echo 'do not run git reset HEAD~1'")
    assert code == 0


def test_allows_literal_string_in_grep() -> None:
    code, _ = _run("grep 'git reset HEAD~1' docs/")
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
