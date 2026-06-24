"""Behavior tests for branch-guard.sh — trunk-based workflow enforcement (TASK-012)."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

HOOK = Path(__file__).resolve().parent.parent / "src" / "core" / "hooks" / "branch-guard.sh"


def _run(command: str, *, tool: str = "Bash", workflow: str | None = None) -> tuple[int, str]:
    # strip both so an inherited COS_WORKTREE_ROOT can't flip the per-op scope tests
    _drop = {"COS_GIT_WORKFLOW", "COS_WORKTREE_ROOT"}
    env = {k: v for k, v in os.environ.items() if k not in _drop}
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


# --- blocked: HEAD-rewriting ops -------------------------------


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


# --- pr mode: positive policy (TASK-516) — branches/worktrees pass, but the
#     shared integration checkout + protected branches stay guarded ----------

# A path containing the worktree marker; the gate only parses it, never runs it.
_WT = "/tmp/repo/.coding-os/worktrees/slug/task-1"


def test_pr_mode_allows_agents_branch_create() -> None:
    code, _ = _run("git checkout -b agents/auth-timeout/abc", workflow="pr")
    assert code == 0


def test_pr_mode_allows_branch_create() -> None:
    # Branches are the pr-mode isolation mechanism — any create is allowed.
    code, _ = _run("git checkout -b feature/foo", workflow="pr")
    assert code == 0


def test_pr_mode_allows_worktree_add() -> None:
    code, _ = _run(f"git worktree add {_WT} origin/main", workflow="pr")
    assert code == 0


def test_pr_mode_blocks_reset_on_shared_checkout() -> None:
    code, err = _run("git reset HEAD~3", workflow="pr")
    assert code == 2
    assert "worktree" in err.lower()


def test_pr_mode_allows_reset_in_worktree() -> None:
    code, _ = _run(f"cd {_WT} && git reset HEAD~3", workflow="pr")
    assert code == 0


def test_pr_mode_blocks_commit_on_shared_checkout() -> None:
    code, err = _run("git commit -m wip", workflow="pr")
    assert code == 2
    assert "worktree" in err.lower()


def test_pr_mode_allows_commit_in_worktree() -> None:
    code, _ = _run(f"cd {_WT} && git commit -m wip", workflow="pr")
    assert code == 0


def test_pr_mode_blocks_push_to_protected() -> None:
    code, _ = _run("git push origin production", workflow="pr")
    assert code == 2


def test_pr_mode_blocks_push_to_integration() -> None:
    code, _ = _run("git push origin main", workflow="pr")
    assert code == 2


def test_pr_mode_allows_push_agents_branch() -> None:
    # The sanctioned push runs from INSIDE the worktree (HEAD is agents/* there).
    code, _ = _run(f"cd {_WT} && git push --force-with-lease -u origin HEAD", workflow="pr")
    assert code == 0


def test_pr_mode_blocks_push_heads_shorthand_protected() -> None:
    # heads/<branch> is a valid refspec git resolves to refs/heads/<branch>; it must
    # normalize like refs/heads/ or it slips the membership test (the confirmed bypass).
    code, _ = _run("git push origin HEAD:heads/production", workflow="pr")
    assert code == 2


def test_pr_mode_blocks_bare_push_from_shared_checkout() -> None:
    # On the shared checkout the current branch IS integration; a bare/HEAD push
    # advances it outside PR+CI.
    code, _ = _run("git push", workflow="pr")
    assert code == 2
    code, _ = _run("git push -u origin HEAD", workflow="pr")
    assert code == 2


def test_pr_mode_allows_explicit_agents_push_from_shared() -> None:
    # Naming an explicit non-blocked destination refspec is provably safe even from shared.
    code, _ = _run("git push origin HEAD:agents/auth/abc", workflow="pr")
    assert code == 0


def test_pr_mode_blocks_push_default_matching() -> None:
    # `-c push.default=matching` pushes every same-name branch incl. integration; the
    # `-c` global is stripped before _pr_check, so it must be caught on the raw tokens.
    code, _ = _run("git -c push.default=matching push", workflow="pr")
    assert code == 2


def test_pr_mode_blocks_checkout_force_create_integration() -> None:
    code, _ = _run("git checkout -B main", workflow="pr")
    assert code == 2


def test_pr_mode_blocks_switch_force_create_protected() -> None:
    code, _ = _run("git switch -C production", workflow="pr")
    assert code == 2


def test_pr_mode_blocks_worktree_add_onto_protected() -> None:
    # Checking the integration/protected line out into a worktree would let commits
    # land on it via the worktree's own (otherwise-allowed) HEAD path.
    code, _ = _run(f"git worktree add {_WT} main", workflow="pr")
    assert code == 2


def test_pr_mode_allows_worktree_add_agents_branch() -> None:
    code, _ = _run(f"git worktree add -b agents/auth/abc {_WT} origin/main", workflow="pr")
    assert code == 0


def test_pr_mode_blocks_shared_reset_via_explicit_C_from_worktree_cwd() -> None:
    # finding 5: scope is per git-op — `git -C <main>` targets the shared checkout
    # even when a `cd <worktree>` precedes it, so the HEAD-rewrite must BLOCK.
    code, err = _run(f"cd {_WT} && git -C /tmp/repo reset HEAD~3", workflow="pr")
    assert code == 2
    assert "worktree" in err.lower()


def test_pr_mode_allows_reset_via_explicit_C_into_worktree() -> None:
    # the inverse: -C points at the worktree, so the op is worktree-scoped → allow,
    # regardless of the shared-checkout cwd.
    code, _ = _run(f"cd /tmp/repo && git -C {_WT} reset HEAD~3", workflow="pr")
    assert code == 0


def test_pr_mode_blocks_push_mirror() -> None:
    code, _ = _run("git push --mirror origin", workflow="pr")
    assert code == 2


def test_pr_mode_blocks_push_all() -> None:
    code, _ = _run("git push --all origin", workflow="pr")
    assert code == 2


def test_pr_mode_blocks_push_force_refspec_integration() -> None:
    code, _ = _run("git push origin +main", workflow="pr")
    assert code == 2


# --- hardening: bypass probes (must BLOCK after this task) -------


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


# --- hardening: false-positive probes (must ALLOW after this task)


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


# --- post-review hardening: residual nesting / separators -------


def test_blocks_doubly_nested_sh_c() -> None:
    code, _ = _run("sh -c \"sh -c 'git reset HEAD~1'\"")
    assert code == 2


def test_blocks_newline_separated_commands() -> None:
    # A literal newline must be treated as a command separator, not folded
    # into a single space.
    code, _ = _run("git status\ngit reset HEAD~1")
    assert code == 2


def test_blocks_backtick_subshell() -> None:
    code, _ = _run("`git reset HEAD~1`")
    assert code == 2


def test_blocks_backtick_nested_in_echo() -> None:
    # `echo `git reset HEAD~1`` — backtick body must be inspected even
    # when the outer command name is `echo`.
    code, _ = _run("echo `git reset HEAD~1`")
    assert code == 2


def test_blocks_multi_level_nested_shells() -> None:
    code, _ = _run('bash -c "sh -c \\"git checkout feature-x\\""')
    assert code == 2


def test_allows_escaped_backticks_in_commit_message() -> None:
    # `\`git reset HEAD~1\`` inside a `git commit -m` arg is an inert
    # literal — bash does not execute escaped backticks. Must NOT block.
    code, _ = _run("git commit -m 'see \\`git reset HEAD~1\\` for the unsafe form' foo.py")
    assert code == 0


# --- git rebase blocks (history rewrite on trunk) ----------------


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


def test_blocks_rebase_via_git_dash_C() -> None:
    code, _ = _run("git -C /tmp rebase main")
    assert code == 2


def test_blocks_rebase_in_nested_sh_c() -> None:
    code, _ = _run("sh -c 'git rebase -i HEAD~3'")
    assert code == 2


def test_pr_mode_blocks_rebase_on_shared_checkout() -> None:
    code, _ = _run("git rebase main", workflow="pr")
    assert code == 2


def test_pr_mode_allows_rebase_in_worktree_via_dash_C() -> None:
    code, _ = _run(f"git -C {_WT} rebase FETCH_HEAD", workflow="pr")
    assert code == 0


def test_pr_mode_allows_rebase_abort_anywhere() -> None:
    code, _ = _run("git rebase --abort", workflow="pr")
    assert code == 0


# --- TASK-528: pr-policy leak probes — refspec push / merge / cherry-pick /
#     branch -f / update-ref must NOT bypass the protected wall ---------------


def test_pr_mode_blocks_push_fully_qualified_integration_refspec() -> None:
    # `_push_targets` must strip refs/heads/ before the membership test.
    code, _ = _run("git push origin HEAD:refs/heads/main", workflow="pr")
    assert code == 2


def test_pr_mode_blocks_push_force_qualified_refspec() -> None:
    code, _ = _run("git push origin +refs/heads/main", workflow="pr")
    assert code == 2


def test_pr_mode_blocks_push_qualified_protected_refspec() -> None:
    code, _ = _run("git push origin HEAD:refs/heads/production", workflow="pr")
    assert code == 2


def test_pr_mode_blocks_push_delete_integration_refspec() -> None:
    # `git push origin :refs/heads/main` deletes remote main — must BLOCK.
    code, _ = _run("git push origin :refs/heads/main", workflow="pr")
    assert code == 2


def test_pr_mode_blocks_merge_on_shared_checkout() -> None:
    code, err = _run("git merge agents/auth/abc", workflow="pr")
    assert code == 2
    assert "worktree" in err.lower()


def test_pr_mode_allows_merge_in_worktree() -> None:
    code, _ = _run(f"cd {_WT} && git merge agents/auth/abc", workflow="pr")
    assert code == 0


def test_pr_mode_blocks_cherry_pick_on_shared_checkout() -> None:
    code, _ = _run("git cherry-pick abc1234", workflow="pr")
    assert code == 2


def test_pr_mode_allows_cherry_pick_in_worktree_via_dash_C() -> None:
    code, _ = _run(f"git -C {_WT} cherry-pick abc1234", workflow="pr")
    assert code == 0


def test_pr_mode_allows_merge_abort_anywhere() -> None:
    code, _ = _run("git merge --abort", workflow="pr")
    assert code == 0


def test_pr_mode_allows_cherry_pick_continue_anywhere() -> None:
    code, _ = _run("git cherry-pick --continue", workflow="pr")
    assert code == 0


def test_pr_mode_blocks_branch_force_move_integration() -> None:
    code, err = _run("git branch -f main HEAD~1", workflow="pr")
    assert code == 2
    assert "protected" in err.lower() or "ref" in err.lower()


def test_pr_mode_blocks_branch_delete_integration() -> None:
    code, _ = _run("git branch -D main", workflow="pr")
    assert code == 2


def test_pr_mode_blocks_branch_rename_onto_integration() -> None:
    code, _ = _run("git branch -m oldname main", workflow="pr")
    assert code == 2


def test_pr_mode_blocks_branch_force_move_even_in_worktree() -> None:
    # refs are shared across worktrees via the common dir → worktree scope is no
    # protection for a direct ref rewrite of a blocked branch.
    code, _ = _run(f"git -C {_WT} branch -f main HEAD~1", workflow="pr")
    assert code == 2


def test_pr_mode_blocks_update_ref_integration() -> None:
    code, _ = _run("git update-ref refs/heads/main HEAD~1", workflow="pr")
    assert code == 2


def test_pr_mode_blocks_update_ref_delete_protected() -> None:
    code, _ = _run("git update-ref -d refs/heads/production", workflow="pr")
    assert code == 2


def test_pr_mode_blocks_update_ref_stdin() -> None:
    # `--stdin` reads ref commands we can't inspect → fail closed.
    code, _ = _run("git update-ref --stdin", workflow="pr")
    assert code == 2


# --- TASK-528 false-positive probes — the agents/* flow must stay ALLOWED ----


def test_pr_mode_allows_branch_delete_agents_cleanup() -> None:
    # `cos pr cleanup` deletes the agent branch — must NOT block.
    code, _ = _run("git branch -D agents/auth/abc", workflow="pr")
    assert code == 0


def test_pr_mode_allows_branch_create_agents() -> None:
    code, _ = _run("git branch agents/foo/123", workflow="pr")
    assert code == 0


def test_pr_mode_allows_branch_force_create_agents_from_main() -> None:
    # force-create an agents/* branch AT main's commit — startpoint main is a
    # read-only source, not the ref being written, so this is allowed.
    code, _ = _run("git branch -f agents/x/1 main", workflow="pr")
    assert code == 0


def test_pr_mode_allows_update_ref_agents() -> None:
    code, _ = _run("git update-ref refs/heads/agents/x/1 HEAD", workflow="pr")
    assert code == 0


# --- TASK-528 trunk-mode must stay byte-identical (no new blocks) ------------


def test_trunk_push_refspec_unchanged() -> None:
    # trunk's publish path IS push-to-main — the pr push guard must not leak in.
    code, _ = _run("git push origin HEAD:refs/heads/main")
    assert code == 0


def test_trunk_merge_unchanged() -> None:
    code, _ = _run("git merge feature-x")
    assert code == 0


def test_trunk_update_ref_unchanged() -> None:
    code, _ = _run("git update-ref refs/heads/main HEAD~1")
    assert code == 0


def test_trunk_branch_force_unchanged() -> None:
    code, _ = _run("git branch -f main HEAD~1")
    assert code == 0
