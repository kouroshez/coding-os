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


def test_pr_mode_blocks_push_double_heads_prefix_protected() -> None:
    # A doubled ref-namespace prefix must normalize to the bare name too — else
    # refs/heads/refs/heads/production survives a one-level strip and slips the wall (D1).
    code, _ = _run("git push origin HEAD:refs/heads/refs/heads/production", workflow="pr")
    assert code == 2


def test_pr_mode_blocks_update_ref_double_prefix_protected() -> None:
    code, _ = _run("git update-ref refs/heads/refs/heads/production HEAD", workflow="pr")
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


# --- TASK-543: worktree-spoof + fetch-refspec leaks --------------------------


def test_pr_mode_blocks_reset_via_traversal_spoof_into_shared() -> None:
    # `.../worktrees/x/../../../..` realpath-resolves OUT of the worktree into the
    # shared checkout — the old raw-string OR-arm wrongly treated it as worktree.
    code, err = _run(f"cd {_WT}/../../../.. && git reset HEAD~3", workflow="pr")
    assert code == 2
    assert "worktree" in err.lower()


def test_pr_mode_blocks_fetch_refspec_to_integration() -> None:
    code, err = _run("git fetch origin master:main", workflow="pr")
    assert code == 2
    assert "protected" in err.lower() or "ref" in err.lower()


def test_pr_mode_blocks_fetch_delete_refspec_protected() -> None:
    # `git fetch origin :production` updates/deletes the local protected ref.
    code, _ = _run("git fetch origin :production", workflow="pr")
    assert code == 2


def test_pr_mode_allows_colon_free_fetch() -> None:
    # The legit pr-mode fetch never uses a colon — must NOT block.
    code, _ = _run("git fetch origin main", workflow="pr")
    assert code == 0


def test_pr_mode_allows_fetch_refspec_to_agents() -> None:
    code, _ = _run("git fetch origin main:agents/x/1", workflow="pr")
    assert code == 0


def test_pr_mode_blocks_pull_refspec_to_integration() -> None:
    # `git pull origin x:main` is fetch+merge with identical refspec syntax — it
    # force-writes the local protected ref exactly like the fetch bypass (finding 3).
    code, err = _run("git pull origin master:main", workflow="pr")
    assert code == 2
    assert "protected" in err.lower() or "ref" in err.lower()


def test_pr_mode_blocks_pull_delete_refspec_protected() -> None:
    code, _ = _run("git pull origin :production", workflow="pr")
    assert code == 2


def test_pr_mode_allows_colon_free_pull() -> None:
    # A plain pull (the documented trunk-integration step) has no colon — must NOT block.
    code, _ = _run("git pull origin main", workflow="pr")
    assert code == 0


def test_trunk_fetch_unchanged() -> None:
    # The fetch arm is pr-only; trunk must stay byte-identical.
    code, _ = _run("git fetch origin master:main")
    assert code == 0


# --- TASK-528 trunk-mode must stay byte-identical (no new blocks) ------------


def test_trunk_push_refspec_unchanged() -> None:
    # trunk's publish path IS push-to-main — the pr push guard must not leak in.
    code, _ = _run("git push origin HEAD:refs/heads/main")
    assert code == 0


def test_trunk_merge_unchanged() -> None:
    code, _ = _run("git merge feature-x")
    assert code == 0


# --- TASK-562: trunk now guards the integration/protected ref at PARITY with
#     pr-mode (force-rewrite / rename / delete / update-ref of main|production|
#     HEAD). merge / cherry-pick / push-to-main stay ALLOWED — that is the trunk
#     publish path (see test_trunk_merge_unchanged / test_trunk_push_refspec_unchanged).
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


def test_trunk_allows_branch_rename_feature() -> None:
    # Renaming a NON-protected feature branch (two positionals, neither blocked)
    # stays legit branch admin in trunk.
    code, _ = _run("git branch -m oldfeature newfeature")
    assert code == 0


def test_trunk_allows_update_ref_non_protected() -> None:
    code, _ = _run("git update-ref refs/heads/feature-x HEAD")
    assert code == 0


# --- TASK-565: code-review regressions — the ref/filter parser must not block
#     read-only branch list forms or be fooled by `update-ref -m <reason>`. -------
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


def test_pr_mode_allows_branch_filter_forms() -> None:
    # The shared _pr_branch_blocks fix benefits pr-mode too.
    code, _ = _run("git branch --contains main", workflow="pr")
    assert code == 0


def test_pr_mode_blocks_update_ref_reflog_message_integration() -> None:
    code, _ = _run("git update-ref -m wip refs/heads/main HEAD~1", workflow="pr")
    assert code == 2


# --- TASK-567 (F4): commit -a sweep + history-rewrite verbs ----------------


def test_trunk_blocks_commit_dash_a() -> None:
    # `git commit -a/--all` sweeps a concurrent session's WIP — trunk wants paths.
    for cmd in ("git commit -a -m x", "git commit --all -m x", "git commit -am x"):
        code, _ = _run(cmd)
        assert code == 2, cmd


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
    code, _ = _run("/usr/bin/git commit -a -m x")
    assert code == 2


def test_trunk_blocks_history_rewrite_verbs() -> None:
    for cmd in (
        "git filter-branch --tree-filter true HEAD",
        "git filter-repo --path src",
    ):
        code, err = _run(cmd)
        assert code == 2, cmd
        assert "history" in err.lower()


def test_trunk_blocks_symbolic_ref_write_allows_read() -> None:
    code, _ = _run("git symbolic-ref HEAD refs/heads/other")
    assert code == 2
    for read in ("git symbolic-ref HEAD", "git symbolic-ref --short HEAD"):
        code, _ = _run(read)
        assert code == 0, read


def test_pr_mode_blocks_history_rewrite_verbs() -> None:
    # Parity: filter-branch rewrites the shared object db even in pr-mode.
    code, _ = _run("git filter-branch --tree-filter true HEAD", workflow="pr")
    assert code == 2


# --- TASK-571: separator-prefixed dangerous ops still block (own segmenter) ---


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
