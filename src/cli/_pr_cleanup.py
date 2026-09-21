"""Reclaiming one finished worktree: cleanup.

Private module of pr_commands.py — import through that facade.
"""

from __future__ import annotations

import json
import sys

try:
    import fcntl
except ImportError:  # non-POSIX (Windows) — the reaper lock degrades to a no-op
    fcntl = None  # type: ignore[assignment]

import click

from cli._pr_shared import (
    _agent_session,
    _branch_recoverable,
    _emit,
    _gh_ready,
    _git,
    _heal_budget_clear,
    _integration_branch,
    _preserve_reaped,
    _resolve_repo,
    _resolve_worktree,
    _run,
    _sanitize,
    _session_state,
    pr_group,
)


def _pr_state(repo: str, branch: str) -> str:
    # "merged" | "closed" | "open" | "none" | "unknown" — drives the cleanup
    # merge-gate so an open PR's worktree isn't destroyed mid-flight.
    if not _gh_ready():
        return "unknown"
    listing = _run(
        ["gh", "pr", "list", "--head", branch, "--state", "all", "--json", "state,mergedAt"],
        cwd=repo,
    )
    if listing.returncode != 0:
        return "unknown"
    try:
        prs = json.loads(listing.stdout or "[]")
    except json.JSONDecodeError:
        return "unknown"
    if not prs:
        return "none"
    if prs[0].get("mergedAt"):
        return "merged"
    return str(prs[0].get("state", "")).lower() or "unknown"


@pr_group.command(
    "cleanup",
    help="Remove the worktree + delete the branch + prune (merge-gated; --force to override).",
)
@click.option("--task", "task_id", default=None)
@click.option("--adhoc", is_flag=True)
@click.option("--repo", "repo_opt", default=None)
@click.option(
    "--force",
    is_flag=True,
    help="Remove even if the PR is open / the branch is unpushed (human override).",
)
@click.option("--json", "as_json", is_flag=True)
def pr_cleanup(
    task_id: str | None, adhoc: bool, repo_opt: str | None, force: bool, as_json: bool
) -> None:
    repo = _resolve_repo(repo_opt)
    session = _agent_session()
    task_slug = "adhoc" if adhoc else _sanitize(task_id) if task_id else None
    if task_slug is None:
        raise click.ClickException("cos pr cleanup needs --task <id> or --adhoc.")
    wt, branch = _resolve_worktree(repo, task_slug, session)
    _preserved_bundle: str | None = None  # set when a drifted/peer dirty tree is bundled

    # Merge-gate: only destroy the worktree+branch once work has landed
    # (merged/closed) or is fully on origin; --force is the human override.
    if not force:
        # Ownership gate (review finding 2): under session drift the single-candidate
        # fallback in _resolve_worktree can resolve a live PEER's worktree (same task
        # slug, different session) — destroying it would wipe active peer work. Refuse
        # only when the owner session is provably LIVE; a drifted-gone ("unknown") or
        # dead ("offline") owner still cleans up, preserving the drift path.
        owner_session = branch.rsplit("/", 1)[-1]
        if owner_session != session and _session_state(owner_session, repo) == "live":
            _emit(
                {
                    "removed": False,
                    "branch": branch,
                    "owner_session": owner_session,
                    "action": "worktree belongs to another live session — not removing; its owner or 'cos pr reap' will GC it, or re-run with --force",
                },
                as_json,
            )
            sys.exit(1)
        state = _pr_state(repo, branch)
        if state == "open":
            _emit(
                {
                    "removed": False,
                    "branch": branch,
                    "pr_state": "open",
                    "action": "PR still open — not removing; merge/close it, or re-run with --force",
                },
                as_json,
            )
            sys.exit(1)
        recoverable = _branch_recoverable(repo, branch, _integration_branch(repo))
        # Unpushed work with no landing PR: refuse and tell the user to submit, keeping
        # the branch intact — friendlier than bundle+delete for an interactive cleanup,
        # and the reaper is the GC path for a genuinely dead owner.
        if state in {"none", "unknown"} and not recoverable:
            _emit(
                {
                    "removed": False,
                    "branch": branch,
                    "pr_state": state,
                    "action": "branch has local commits not on origin — 'cos pr submit' first, or --force to discard",
                },
                as_json,
            )
            sys.exit(1)
        # Preserve-before-destroy net ( H): for any OTHER state (merged/closed)
        # a branch that is unrecoverable (squash-merge, or extra local commits not on
        # origin) or has a dirty tree must be bundled before `branch -D`. The old code
        # bundled only a DIRTY drifted tree, so a CLEAN-tree merged branch with unpushed
        # commits was discarded with NO bundle. A FAILED status reads as "maybe dirty"
        # so a transient git error can't pass as clean and wipe work (review finding F).
        # Mirrors _reap_one's safety arm — cleanup and reap no longer diverge.
        _status = _git(["status", "--porcelain"], cwd=wt)
        dirty = _status.returncode != 0 or bool(_status.stdout.strip())
        if not recoverable or dirty:
            _preserved_bundle = _preserve_reaped(repo, wt, branch)
            if _preserved_bundle is None:
                _emit(
                    {
                        "removed": False,
                        "branch": branch,
                        "pr_state": state,
                        "action": "branch has unpushed commits or an uncommitted tree and preservation failed — recover it manually, or --force to discard.",
                    },
                    as_json,
                )
                sys.exit(1)

    _git(["worktree", "unlock", str(wt)], cwd=repo)  # release the pr-mode live-lock
    removed_wt = _git(["worktree", "remove", "--force", str(wt)], cwd=repo).returncode == 0
    deleted_branch = _git(["branch", "-D", branch], cwd=repo).returncode == 0
    _git(["worktree", "prune"], cwd=repo)
    _heal_budget_clear(repo, branch)  # branch is done — drop its heal budget (finding 8)
    _emit(
        {
            "worktree_removed": removed_wt,
            "branch_deleted": deleted_branch,
            "worktree": str(wt),
            "forced": force,
            "preserved_bundle": _preserved_bundle,
        },
        as_json,
    )
