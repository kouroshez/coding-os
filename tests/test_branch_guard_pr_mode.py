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


def test_pr_mode_blocks_push_to_protected_branch_pattern() -> None:
    code, _ = _run(
        "git push origin release/v1",
        workflow="pr",
        extra_env={"COS_GIT_PROTECTED_BRANCHES": "release/*"},
    )
    assert code == 2


def test_pr_mode_blocks_refspec_push_to_protected_branch_pattern() -> None:
    code, _ = _run(
        "git push origin HEAD:refs/heads/release/v1",
        workflow="pr",
        extra_env={"COS_GIT_PROTECTED_BRANCHES": "release/*"},
    )
    assert code == 2


def test_pr_mode_allows_push_outside_protected_branch_pattern() -> None:
    code, _ = _run(
        "git push origin HEAD:release-candidate",
        workflow="pr",
        extra_env={"COS_GIT_PROTECTED_BRANCHES": "release/*"},
    )
    assert code == 0


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


def test_pr_mode_blocks_rebase_on_shared_checkout() -> None:
    code, _ = _run("git rebase main", workflow="pr")
    assert code == 2


def test_pr_mode_allows_rebase_in_worktree_via_dash_C() -> None:
    code, _ = _run(f"git -C {_WT} rebase FETCH_HEAD", workflow="pr")
    assert code == 0


def test_pr_mode_allows_rebase_abort_anywhere() -> None:
    code, _ = _run("git rebase --abort", workflow="pr")
    assert code == 0


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


def test_pr_mode_blocks_update_ref_protected_branch_pattern() -> None:
    code, _ = _run(
        "git update-ref refs/heads/release/v1 HEAD~1",
        workflow="pr",
        extra_env={"COS_GIT_PROTECTED_BRANCHES": "release/*"},
    )
    assert code == 2


def test_pr_mode_blocks_update_ref_stdin() -> None:
    # `--stdin` reads ref commands we can't inspect → fail closed.
    code, _ = _run("git update-ref --stdin", workflow="pr")
    assert code == 2


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


def test_pr_mode_allows_branch_filter_forms() -> None:
    # The shared _pr_branch_blocks fix benefits pr-mode too.
    code, _ = _run("git branch --contains main", workflow="pr")
    assert code == 0


def test_pr_mode_blocks_update_ref_reflog_message_integration() -> None:
    code, _ = _run("git update-ref -m wip refs/heads/main HEAD~1", workflow="pr")
    assert code == 2


def test_pr_mode_blocks_history_rewrite_verbs() -> None:
    # Parity: filter-branch rewrites the shared object db even in pr-mode.
    code, _ = _run("git filter-branch --tree-filter true HEAD", workflow="pr")
    assert code == 2
