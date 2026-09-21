"""Publishing work: submit and land.

Private module of pr_commands.py — import through that facade.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

try:
    import fcntl
except ImportError:  # non-POSIX (Windows) — the reaper lock degrades to a no-op
    fcntl = None  # type: ignore[assignment]

import click

from cli._pr_shared import (
    _AUTONOMY_LEVELS,
    _agent_session,
    _emit,
    _env_int,
    _escalate_blocked,
    _gh_ready,
    _git,
    _git_out,
    _git_settings,
    _integration_branch,
    _preflight,
    _resolve_repo,
    _resolve_worktree,
    _run,
    _sanitize,
    _unprotected_warning,
    pr_group,
)


def _commit_count(cwd: str | Path, rev_range: str) -> int:
    # 0 on any error (unresolved range) so the local-rung report fails toward
    # "nothing to integrate" rather than a crash.
    out = _git_out(["rev-list", "--count", rev_range], cwd=cwd)
    try:
        return int(out)
    except ValueError:
        return 0


def _autonomy_level(repo: str | None = None) -> str:
    # Trust Spectrum: draft never arms auto-merge; auto_merge/autonomous do.
    # Explicit env var wins; else the consumer's saved autonomy_level. The Hub API
    # edge validates the rung (Literal), but hub-settings.json can also be written
    # by the CLI or by hand — so validate HERE, where the value is consumed, and
    # fall back to the safe 'draft' on an unknown rung rather than letting a typo
    # silently behave as draft while reporting itself as the typo'd value.
    raw = ""
    env = os.environ.get("COS_GIT_AUTONOMY")
    if env and env.strip():
        raw = env.strip()
    elif repo is not None:
        level = _git_settings(repo).get("autonomy_level")
        if isinstance(level, str) and level.strip():
            raw = level.strip()
    if not raw:
        return "draft"
    if raw not in _AUTONOMY_LEVELS:
        click.echo(
            f"cos pr: unknown autonomy_level {raw!r} — falling back to 'draft' "
            f"(valid: {', '.join(_AUTONOMY_LEVELS)})",
            err=True,
        )
        return "draft"
    return raw


@pr_group.command(
    "submit", help="Publish: rebase onto FETCH_HEAD, lease-push, open PR, arm auto-merge."
)
@click.option("--task", "task_id", default=None)
@click.option("--adhoc", is_flag=True)
@click.option("--repo", "repo_opt", default=None)
@click.option("--integration", default=None)
@click.option("--title", default=None, help="PR title (default: branch name).")
@click.option("--body", default="", help="PR body.")
@click.option("--json", "as_json", is_flag=True)
def pr_submit(
    task_id: str | None,
    adhoc: bool,
    repo_opt: str | None,
    integration: str | None,
    title: str | None,
    body: str,
    as_json: bool,
) -> None:
    repo = _resolve_repo(repo_opt)
    integration = integration or _integration_branch(repo)
    session = _agent_session()
    task_slug = "adhoc" if adhoc else _sanitize(task_id) if task_id else None
    if task_slug is None:
        raise click.ClickException("cos pr submit needs --task <id> or --adhoc.")
    wt, branch = _resolve_worktree(repo, task_slug, session)
    if not (wt / ".git").exists():
        raise click.ClickException(f"no open worktree at {wt} — run 'cos pr open' first.")

    # `local` rung: commit-only, never push. Short-circuits before the
    # capability probe so a repo with no remote is the intended mode, not a degrade.
    autonomy = _autonomy_level(repo)
    if autonomy == "local":
        ahead = _commit_count(wt, f"{integration}..{branch}")
        behind = _commit_count(wt, f"{branch}..{integration}")
        if ahead == 0:
            action = f"no commits to integrate yet — commit your work in {wt}, then re-run 'cos pr submit'."
        else:
            stale = (
                f" branch is {behind} behind '{integration}' — rebase before integrating."
                if behind
                else ""
            )
            action = (
                f"{ahead} commit(s) committed locally, not pushed (autonomy=local) — review with "
                f"'git diff {integration}..{branch}', then a HUMAN integrates it in plain git "
                f"OUTSIDE the agent (the agent is branch-guard-blocked from merging the shared "
                f"checkout): 'git switch {integration} && git merge --no-ff {branch}'.{stale}"
            )
        _emit(
            {
                "branch": branch,
                "pushed": False,
                "autonomy_level": "local",
                "merge_status": "local",
                "commits_ahead": ahead,
                "behind": behind,
                "stale": behind > 0,
                "action": action,
            },
            as_json,
        )
        return

    cap = _preflight(repo, integration)
    if not cap["pr_ok"]:
        _emit(
            {
                "mode": "degraded-trunk",
                "missing": ",".join(cap["missing"]),
                "action": "pr-mode unavailable — commit on the worktree and integrate via the trunk path",
            },
            as_json,
        )
        sys.exit(1)

    # Circuit-breaker BEFORE any push — refuse past the per-session open-PR cap
    # so a red / quota-dead CI can't grow open PRs without bound, and
    # a capped submit never orphans a pushed branch with no PR (§8, findings 7/9).
    cap_max = _env_int("COS_PR_MAX_OPEN", 5)
    # Count against the resolved branch's session, not the process session — under
    # session-id drift (_resolve_worktree) `branch` carries the original session
    # while `session` is a fresh pid-<getpid>; counting the latter reads 0 and
    # bypasses the cap on exactly the branch being pushed (review finding 1).
    open_prs = _open_pr_count(repo, branch.rsplit("/", 1)[-1])
    # open_prs < 0 = could not determine (gh down / quota-dead) — fail SAFE and
    # refuse the push rather than count it as "0 open PRs" (M1).
    unknown = open_prs < 0
    if unknown or open_prs >= cap_max:
        _emit(
            {
                "branch": branch,
                "pushed": False,
                "circuit_breaker": "open",
                "open_prs": "unknown" if unknown else open_prs,
                "cap": cap_max,
                "action": (
                    "open-PR count unknown (gh down/quota) — not pushing; restore gh, then retry"
                    if unknown
                    else "open-PR cap reached — not pushing; drain existing PRs first"
                ),
            },
            as_json,
        )
        sys.exit(1)

    # Rebase onto the PINNED fetched ref (FETCH_HEAD), never the shared moving
    # branch — branch-guard permits this because the op is worktree-scoped (§5).
    _git(["fetch", "origin", integration], cwd=wt)
    rebase = _git(["rebase", "FETCH_HEAD"], cwd=wt)
    if rebase.returncode != 0:
        _git(["rebase", "--abort"], cwd=wt)
        raise click.ClickException(
            f"rebase onto origin/{integration} conflicted — resolve in the worktree, then retry."
        )

    # sha-pinned lease: refresh origin/<branch> first so the lease pins to its
    # TRUE current remote sha (no-op on a first push); empty lease for a first
    # push. With --force-if-includes this never clobbers a concurrent push.
    _git(["fetch", "origin", branch], cwd=wt)
    remote_sha = _git_out(["rev-parse", f"origin/{branch}"], cwd=wt)
    lease = (
        f"--force-with-lease={branch}:{remote_sha}"
        if remote_sha
        else f"--force-with-lease={branch}"
    )
    push = _git(["push", lease, "--force-if-includes", "-u", "origin", branch], cwd=wt)
    if push.returncode != 0:
        raise click.ClickException(f"push rejected (lease/connectivity):\n{push.stderr.strip()}")

    pr = _run(
        [
            "gh",
            "pr",
            "create",
            "--base",
            integration,
            "--head",
            branch,
            "--title",
            title or branch,
            "--body",
            body or f"agent branch {branch}",
        ],
        cwd=wt,
    )
    pr_ok = pr.returncode == 0
    arm_allowed = autonomy in ("auto_merge", "autonomous")
    armed = False
    if pr_ok and arm_allowed and cap["required_check"]:
        # Auto-merge ONLY when a required check exists, else the PR merges with
        # no CI gate. Stays armed; merges itself once the check is green.
        armed = _run(["gh", "pr", "merge", "--auto", "--squash"], cwd=wt).returncode == 0

    # auto_merge + a required REVIEW (CODEOWNERS / ruleset) = armed but unmergeable
    # until a human approves — surface it so submit never reports "will merge" while
    # the PR silently waits on an approval the agent can't give.
    review_required = armed and _pr_review_required(wt, branch)

    # A no-required-check repo silently no-ops `gh pr merge --auto`; surface the
    # outcome so submit never strands an open PR with no signal.
    if armed and review_required:
        merge_status = "auto-merge-armed-awaiting-review"
        action = (
            f"PR auto-merge armed, but '{integration}' requires an approving review — it "
            f"stays open until a human approves, then merges itself. Approve the PR (the "
            f"agent never self-approves)."
        )
    elif armed:
        merge_status = "auto-merge-armed"
        action = f"PR merges itself once the required check on '{integration}' is green"
    elif not pr_ok:
        merge_status = "pr-create-failed"
        action = pr.stderr.strip() or "gh pr create failed — PR not opened; branch is pushed"
    elif not arm_allowed:
        # draft autonomy: the PR is intentionally human-merged, regardless of CI.
        merge_status = "draft"
        action = (
            f"PR open in '{autonomy}' autonomy — a human merges it. Set "
            f"autonomy_level=auto_merge in Hub Config→Git to arm auto-merge."
        )
    elif not cap["required_check"]:
        merge_status = "degraded-no-required-check"
        action = (
            f"PR open but auto-merge NOT armed: no required status check on "
            f"'{integration}'. Add a required check (pr-workflow.md §11) and re-run "
            f"'cos pr submit', or merge the PR manually."
        )
    else:
        merge_status = "arm-failed"
        action = (
            "required check exists but 'gh pr merge --auto' did not arm — check gh auth/permissions"
        )

    # H3: auto_merge/autonomous + no required check = a silent deadlock (the PR will
    # neither merge nor fail). Escalate the board task to blocked so a human adds the
    # check, instead of leaving an open PR with only a non-fatal stderr line.
    board_blocked = False
    if merge_status == "degraded-no-required-check" and task_id:
        board_blocked = _escalate_blocked(
            repo,
            task_id,
            f"pr-mode auto-merge deadlock: autonomy={autonomy} but '{integration}' has no "
            f"required status check — the PR will neither merge nor fail",
            f"pr-mode auto-merge deadlock (no required check on '{integration}')",
        )
        if board_blocked:
            action += " Task escalated to blocked — add a required check, then re-submit."

    payload = {
        "branch": branch,
        "pushed": True,
        "pr_created": pr_ok,
        "pr_url": pr.stdout.strip() if pr_ok else "",
        "auto_merge_armed": armed,
        "required_check": cap["required_check"],
        "review_required": review_required,
        "autonomy_level": autonomy,
        "merge_status": merge_status,
        "board_blocked": board_blocked,
        "action": action,
    }
    if cap["unprotected_integration"]:
        payload["warning"] = _unprotected_warning(integration)
    _emit(payload, as_json)


def _land_verify_ok(repo: str) -> bool:
    # local_autonomous lands only after a GREEN local verify — read the same
    # .last-verify.json freshness marker the DoD gate uses (most-recent PASS within
    # the window). Absent / only-FAIL / stale → refuse to land.
    path = Path(repo) / ".coding-os" / ".last-verify.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(data, dict):
        return False
    ttl = _env_int("COS_PR_LAND_VERIFY_TTL", 1800)
    now = int(time.time())
    for suite in data.values():
        if isinstance(suite, dict) and suite.get("status") == "PASS":
            ts = suite.get("ts")
            if isinstance(ts, int) and 0 <= now - ts <= ttl:
                return True
    return False


@pr_group.command(
    "land",
    help="local_autonomous: merge the agent branch onto LOCAL integration after a green "
    "verify, then clean up (zero push/PR/CI).",
)
@click.option("--task", "task_id", default=None)
@click.option("--adhoc", is_flag=True)
@click.option("--repo", "repo_opt", default=None)
@click.option("--integration", default=None)
@click.option(
    "--no-ff/--ff",
    "no_ff",
    default=True,
    help="--no-ff (default) keeps a merge commit; --ff for fast-forward only.",
)
@click.option("--json", "as_json", is_flag=True)
def pr_land(
    task_id: str | None,
    adhoc: bool,
    repo_opt: str | None,
    integration: str | None,
    no_ff: bool,
    as_json: bool,
) -> None:
    repo = _resolve_repo(repo_opt)
    integration = integration or _integration_branch(repo)
    session = _agent_session()
    task_slug = "adhoc" if adhoc else _sanitize(task_id) if task_id else None
    if task_slug is None:
        raise click.ClickException("cos pr land needs --task <id> or --adhoc.")
    wt, branch = _resolve_worktree(repo, task_slug, session)
    if not (wt / ".git").exists():
        raise click.ClickException(f"no open worktree at {wt} — run 'cos pr open' first.")

    # A RED/absent local verify must NOT land — the rung's whole premise is "green first".
    if not _land_verify_ok(repo):
        _emit(
            {
                "branch": branch,
                "landed": False,
                "reason": "verify-not-green",
                "action": "no recent green verify — run the matrix verify in the worktree, then re-run 'cos pr land'.",
            },
            as_json,
        )
        sys.exit(1)

    ahead = _commit_count(wt, f"{integration}..{branch}")
    if ahead == 0:
        _emit(
            {
                "branch": branch,
                "landed": False,
                "reason": "nothing-to-land",
                "action": f"no commits ahead of '{integration}' — commit your work in the worktree first.",
            },
            as_json,
        )
        return

    # Sanctioned land: merge onto LOCAL integration on the SHARED checkout. cos exports
    # COS_PR_LAND so branch-guard recognises this path (an agent's raw `git merge` on the
    # shared tree stays BLOCKED). Zero network — no push, no PR, no CI.
    merge_args = (
        ["merge", "--no-ff", branch, "-m", f"land {branch} (local_autonomous)"]
        if no_ff
        else ["merge", "--ff-only", branch]
    )
    os.environ["COS_PR_LAND"] = "1"
    try:
        merged = _git(merge_args, cwd=repo)
        if merged.returncode != 0:
            _git(["merge", "--abort"], cwd=repo)
            _emit(
                {
                    "branch": branch,
                    "landed": False,
                    "reason": "merge-conflict",
                    "action": f"merge of '{branch}' onto '{integration}' conflicted — aborted; "
                    f"rebase the worktree onto '{integration}', re-verify, then retry 'cos pr land'.",
                },
                as_json,
            )
            sys.exit(1)
        # Landed: the work is on integration, so the worktree+branch are safe to GC (no
        # orphan). Unlock first — `pr open` locks the worktree with the owner stamp, and
        # `worktree remove` refuses a locked tree (same as the reaper's _reap_one).
        _git(["worktree", "unlock", str(wt)], cwd=repo)
        _git(["worktree", "remove", "--force", str(wt)], cwd=repo)
        _git(["branch", "-D", branch], cwd=repo)
        _git(["worktree", "prune"], cwd=repo)
    finally:
        os.environ.pop("COS_PR_LAND", None)

    _emit(
        {
            "branch": branch,
            "landed": True,
            "integration": integration,
            "commits": ahead,
            "action": f"merged {ahead} commit(s) onto local '{integration}'; worktree+branch removed (zero network).",
        },
        as_json,
    )


def _pr_review_required(wt: Path, branch: str) -> bool:
    # Does THIS PR's review gate (branch protection / ruleset / CODEOWNERS) still
    # block merge? Read the PR's own reviewDecision — authoritative where a probe of
    # required_pull_request_reviews would miss ruleset- and CODEOWNERS-driven reviews.
    out = _run(["gh", "pr", "view", branch, "--json", "reviewDecision"], cwd=wt)
    if out.returncode != 0:
        return False
    try:
        decision = json.loads(out.stdout or "{}").get("reviewDecision")
    except json.JSONDecodeError:
        return False
    return str(decision or "").upper() in {"REVIEW_REQUIRED", "CHANGES_REQUESTED"}


def _open_pr_count(repo: str, session: str) -> int:
    # Open PRs for THIS session only (branch agents/<task>/<session>) — the cap is
    # per-session (playbook §8), so a peer's PRs never starve this agent and a
    # stray human agents/* branch never inflates it (finding 7). Returns -1 for
    # "could not determine" (no gh, or `gh pr list` errored/timed out): the count
    # is unknown in exactly the gh-down/quota-dead scenario the breaker exists for,
    # so the submit caller must treat -1 as cap-reached and fail SAFE — counting it
    # as 0 would let the unbounded push through (M1). A genuinely remote-less repo
    # uses the `local` rung and never reaches this.
    if not _gh_ready():
        return -1
    proc = _run(
        [
            "gh",
            "pr",
            "list",
            "--search",
            "head:agents/",
            "--state",
            "open",
            "--json",
            "headRefName",
        ],
        cwd=repo,
    )
    if proc.returncode != 0:
        return -1
    try:
        prs = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        return -1
    return sum(1 for p in prs if str(p.get("headRefName", "")).rsplit("/", 1)[-1] == session)
