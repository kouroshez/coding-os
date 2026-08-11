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


@pytest.mark.parametrize(
    "command",
    [
        "git reset --har HEAD~1",  # --hard abbrev
        "git reset --so HEAD~2",  # --soft abbrev
        "git reset --ha HEAD~1",  # shorter --hard abbrev
        "git reset --mer HEAD~1",  # --merge abbrev
        "git reset --ke HEAD~3",  # --keep abbrev
        "cd src && git reset --har HEAD~1",  # compound prefix
    ],
)
def test_blocks_reset_mode_abbreviation_head_move(command: str) -> None:
    code, _ = _run(command)
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


def test_blocks_newline_separated_commands() -> None:
    # A literal newline must be treated as a command separator, not folded
    # into a single space.
    code, _ = _run("git status\ngit reset HEAD~1")
    assert code == 2


def test_blocks_backtick_subshell() -> None:
    code, _ = _run("`git reset HEAD~1`")
    assert code == 2


def test_blocks_rebase_onto_main() -> None:
    code, err = _run("git rebase main")
    assert code == 2
    assert "rebase" in err.lower()


def test_blocks_rebase_interactive() -> None:
    code, _ = _run("git rebase -i HEAD~3")
    assert code == 2


def test_blocks_rebase_onto_remote() -> None:
    code, _ = _run("git rebase origin/main")
    assert code == 2


def test_blocks_bare_rebase() -> None:
    # `git rebase` with no args defaults to the upstream tracking branch,
    # i.e. still rewrites local commits onto a remote ref.
    code, _ = _run("git rebase")
    assert code == 2


def test_trunk_fetch_unchanged() -> None:
    # The fetch arm is pr-only; trunk must stay byte-identical.
    code, _ = _run("git fetch origin master:main")
    assert code == 0


def test_trunk_push_refspec_unchanged() -> None:
    # trunk's publish path IS push-to-main — the pr push guard must not leak in.
    code, _ = _run("git push origin HEAD:refs/heads/main")
    assert code == 0


def test_trunk_merge_unchanged() -> None:
    code, _ = _run("git merge feature-x")
    assert code == 0


def test_trunk_blocks_branch_force_integration() -> None:
    code, err = _run("git branch -f main HEAD~1")
    assert code == 2
    assert "main" in err or "protected" in err.lower()


def test_trunk_blocks_branch_rename_onto_integration() -> None:
    code, _ = _run("git branch -M oldname main")
    assert code == 2


def test_trunk_blocks_branch_delete_integration() -> None:
    code, _ = _run("git branch -D main")
    assert code == 2


def test_trunk_blocks_update_ref_integration() -> None:
    code, err = _run("git update-ref refs/heads/main HEAD~1")
    assert code == 2
    assert "main" in err or "protected" in err.lower()


def test_trunk_blocks_update_ref_head() -> None:
    # A direct HEAD move via update-ref is an unguarded reset — block it.
    code, _ = _run("git update-ref HEAD HEAD~1")
    assert code == 2


def test_trunk_blocks_update_ref_delete_protected() -> None:
    code, _ = _run("git update-ref -d refs/heads/production")
    assert code == 2


def test_trunk_blocks_branch_delete_protected_branch_pattern() -> None:
    code, _ = _run(
        "git branch -D release/v1",
        extra_env={"COS_GIT_PROTECTED_BRANCHES": "release/*"},
    )
    assert code == 2


def test_trunk_allows_branch_rename_feature() -> None:
    # Renaming a NON-protected feature branch (two positionals, neither blocked)
    # stays legit branch admin in trunk.
    code, _ = _run("git branch -m oldfeature newfeature")
    assert code == 0


def test_trunk_allows_update_ref_non_protected() -> None:
    code, _ = _run("git update-ref refs/heads/feature-x HEAD")
    assert code == 0


def test_trunk_allows_branch_filter_forms() -> None:
    # `git branch --contains/--merged/--points-at main` are read-only LIST queries
    # naming main as a FILTER, not a ref being written — must NOT block.
    for cmd in (
        "git branch --contains main",
        "git branch --merged main",
        "git branch --no-merged main",
        "git branch --points-at main",
        "git branch --list main",
        "git branch -a --contains main",
    ):
        code, _ = _run(cmd)
        assert code == 0, cmd


def test_trunk_allows_branch_copy_from_protected() -> None:
    # `git branch -c main backup` copies FROM main (source untouched) → allow.
    code, _ = _run("git branch -c main backup")
    assert code == 0


def test_trunk_blocks_branch_copy_onto_protected() -> None:
    # Copying ONTO main writes the protected ref → block.
    code, _ = _run("git branch -c feature main")
    assert code == 2


def test_trunk_blocks_force_with_verbose_flag() -> None:
    # `-v` must not mask a force-write of main (the filter-flag guard is narrow).
    code, _ = _run("git branch -v -f main HEAD~1")
    assert code == 2


def test_trunk_blocks_update_ref_reflog_message_main() -> None:
    # `-m <reason>` is a reflog message; the REF operand (main) still must block.
    code, _ = _run("git update-ref -m wip refs/heads/main HEAD~1")
    assert code == 2


def test_trunk_allows_update_ref_reflog_message_feature() -> None:
    # The reflog message 'HEAD'/'main' must not be misread as the ref operand.
    for cmd in (
        "git update-ref -m HEAD refs/heads/feature abc123",
        "git update-ref -m main refs/heads/feature abc123",
    ):
        code, _ = _run(cmd)
        assert code == 0, cmd


def test_trunk_blocks_commit_dash_a() -> None:
    # `git commit -a/--all` sweeps a concurrent session's WIP — trunk wants paths.
    # Assert the REASON (TASK-572): a block with the wrong gate's message would
    # otherwise pass this test (the symbolic-ref/history message also exits 2).
    for cmd in ("git commit -a -m x", "git commit --all -m x", "git commit -am x"):
        code, err = _run(cmd)
        assert code == 2, cmd
        assert "stages every tracked modification" in err, cmd


def test_trunk_allows_explicit_and_amend_commit() -> None:
    for cmd in (
        "git commit -m x",
        "git commit src/x.py -m x",
        "git commit --amend -m x",
        "git commit --allow-empty -m x",
        'git commit -m "-a"',  # message is "-a", not the -a flag
    ):
        code, _ = _run(cmd)
        assert code == 0, cmd


def test_trunk_blocks_path_qualified_commit_dash_a() -> None:
    # A path-qualified git still runs git — must not evade the -a sweep guard.
    code, err = _run("/usr/bin/git commit -a -m x")
    assert code == 2
    assert "stages every tracked modification" in err


def test_trunk_blocks_history_rewrite_verbs() -> None:
    for cmd in (
        "git filter-branch --tree-filter true HEAD",
        "git filter-repo --path src",
    ):
        code, err = _run(cmd)
        assert code == 2, cmd
        assert "history" in err.lower()


def test_trunk_blocks_symbolic_ref_write_allows_read() -> None:
    code, err = _run("git symbolic-ref HEAD refs/heads/other")
    assert code == 2
    assert "protected integration ref" in err  # the symbolic-ref-write reason
    for read in ("git symbolic-ref HEAD", "git symbolic-ref --short HEAD"):
        code, _ = _run(read)
        assert code == 0, read


def test_trunk_blocks_semicolon_prefixed_ops() -> None:
    # branch_guard uses its own `;`-aware _split_segments; a leading non-git word +
    # `;` must NOT hide the dangerous git command (parity with the F-class fix).
    for cmd in (
        "true; git checkout -b feature/foo",
        "git status; git commit -a -m x",
        "echo done; git reset --hard HEAD~1",
    ):
        code, _ = _run(cmd)
        assert code == 2, cmd


def test_pr_blocks_eval_wrapped_push_to_main() -> None:
    code, _ = _run("eval 'git push origin main'", workflow="pr")
    assert code == 2


def test_pr_blocks_pipe_to_sh_push_to_main() -> None:
    code, _ = _run("printf 'git push origin main' | sh", workflow="pr")
    assert code == 2


def test_pr_blocks_herestring_push_to_main() -> None:
    code, _ = _run("sh <<< 'git push origin main'", workflow="pr")
    assert code == 2


def test_pr_blocks_xargs_push() -> None:
    code, _ = _run("echo main | xargs git push origin", workflow="pr")
    assert code == 2


def test_trunk_blocks_eval_wrapped_branch_create() -> None:
    code, _ = _run("eval 'git checkout -b feature/x'", workflow="trunk")
    assert code == 2


def test_trunk_blocks_pipe_to_sh_switch() -> None:
    code, _ = _run("printf 'git switch other' | sh", workflow="trunk")
    assert code == 2


def test_indirection_allows_legit_eval() -> None:
    code, _ = _run("eval 'echo hi'", workflow="pr")
    assert code == 0


def test_indirection_allows_xargs_git_add() -> None:
    code, _ = _run("ls *.txt | xargs git add", workflow="pr")
    assert code == 0


def test_pr_blocks_update_ref_head_shared() -> None:
    code, _ = _run("git update-ref HEAD deadbeef", workflow="pr")
    assert code == 2


def test_pr_blocks_update_ref_delete_head_shared() -> None:
    code, _ = _run("git update-ref -d HEAD", workflow="pr")
    assert code == 2


def test_pr_blocks_update_ref_head_reflog_message() -> None:
    code, _ = _run("git update-ref -m main HEAD deadbeef", workflow="pr")
    assert code == 2


def test_pr_allows_update_ref_feature() -> None:
    code, _ = _run("git update-ref refs/heads/feature deadbeef", workflow="pr")
    assert code == 0


def test_pr_allows_update_ref_head_in_worktree() -> None:
    code, _ = _run(
        "git -C /private/tmp/x/.coding-os/worktrees/slug/task-1 update-ref HEAD deadbeef",
        workflow="pr",
    )
    assert code == 0


def test_pr_blocks_update_ref_stdin_unchanged() -> None:
    code, _ = _run("git update-ref --stdin", workflow="pr")
    assert code == 2


def test_pr_blocks_raw_agent_merge_on_shared_checkout() -> None:
    code, _ = _run("git merge agents/t/1", workflow="pr")
    assert code == 2


def test_pr_allows_sanctioned_land_merge_with_env_signal() -> None:
    code, _ = _run("git merge --no-ff agents/t/1", workflow="pr", extra_env={"COS_PR_LAND": "1"})
    assert code == 0


def test_pr_inline_cos_pr_land_prefix_cannot_forge_the_carve() -> None:
    # The assignment is part of the command (stripped to _env), not the guard's own
    # process env — so it must NOT unlock the merge.
    code, _ = _run("COS_PR_LAND=1 git merge agents/t/1", workflow="pr")
    assert code == 2
