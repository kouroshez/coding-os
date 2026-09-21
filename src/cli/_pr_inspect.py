"""Looking at work in flight: status, triage, conflicts.

Private module of pr_commands.py — import through that facade.
"""

from __future__ import annotations

import json
from pathlib import Path

try:
    import fcntl
except ImportError:  # non-POSIX (Windows) — the reaper lock degrades to a no-op
    fcntl = None  # type: ignore[assignment]

import click

from cli._pr_shared import (
    _emit,
    _gh_ready,
    _git_out,
    _integration_branch,
    _resolve_repo,
    _run,
    _unqualify_head,
    _worktree_root,
    pr_group,
)


@pr_group.command("status", help="List this repo's pr-mode worktrees, branches, and open PRs.")
@click.option("--repo", "repo_opt", default=None)
@click.option(
    "--branch",
    default=None,
    help="Report one agent branch's CI rollup (merged|red|pending|review-required|passing|passing-unarmed|closed|none) — the driver-loop signal.",
)
@click.option("--json", "as_json", is_flag=True)
def pr_status(repo_opt: str | None, branch: str | None, as_json: bool) -> None:
    repo = _resolve_repo(repo_opt)
    if branch:
        # Single-branch CI signal the pr-mode-driver skill branches on.
        _emit({"branch": branch, "ci_rollup": _pr_ci_rollup(repo, branch)}, as_json)
        return
    wt_root = _worktree_root(repo)
    worktrees = []
    if wt_root.is_dir():
        worktrees = sorted(p.name for p in wt_root.iterdir() if p.is_dir())
    branches = [
        b.strip().lstrip("* ").strip()
        for b in _git_out(["branch", "--list", "agents/*"], cwd=repo).splitlines()
        if b.strip()
    ]
    pr_rows: list[dict] = []
    if _gh_ready():
        out = _run(
            [
                "gh",
                "pr",
                "list",
                "--search",
                "head:agents/",
                "--json",
                "number,headRefName,state,mergedAt,statusCheckRollup,isDraft,autoMergeRequest,reviewDecision",
            ],
            cwd=repo,
        )
        if out.returncode == 0:
            try:
                pr_rows = json.loads(out.stdout or "[]")
            except json.JSONDecodeError:
                pr_rows = []
    open_prs = ",".join(f"#{r.get('number')}:{r.get('headRefName')}" for r in pr_rows)
    ci_rollup = ",".join(f"{r.get('headRefName')}={_rollup_state(r)}" for r in pr_rows)
    _emit(
        {
            "worktree_root": str(wt_root),
            "worktrees": ",".join(worktrees) or "(none)",
            "agent_branches": ",".join(branches) or "(none)",
            "open_prs": open_prs or "(none/gh unavailable)",
            "ci_rollup": ci_rollup or "(none)",
        },
        as_json,
    )


def _agent_worktrees(repo: str) -> dict[str, Path]:
    # Map each live agents/* branch → its worktree path from `git worktree list`.
    # Only branches with a worktree appear, so this naturally scopes to the
    # currently-checked-out (i.e. concurrently-active) agents.
    result: dict[str, Path] = {}
    cur: str | None = None
    for line in _git_out(["worktree", "list", "--porcelain"], cwd=repo).splitlines():
        if line.startswith("worktree "):
            cur = line[len("worktree ") :].strip()
        elif line.startswith("branch ") and cur:
            name = _unqualify_head(line[len("branch ") :].strip())
            if name.startswith("agents/"):
                result[name] = Path(cur)
    return result


def _changed_files(repo: str, branch: str, integration: str, wt: Path | None) -> set[str]:
    # The branch's "touched files" = committed diff since it forked the integration
    # line (merge-base, so a moving integration head doesn't distort it) UNION the
    # worktree's still-uncommitted paths (earliest possible pre-detection signal).
    files: set[str] = set()
    base = _git_out(["merge-base", integration, branch], cwd=repo) or integration
    for line in _git_out(["diff", "--name-only", f"{base}..{branch}"], cwd=repo).splitlines():
        if line.strip():
            files.add(line.strip())
    if wt is not None and (wt / ".git").exists():
        for line in _git_out(["status", "--porcelain"], cwd=wt).splitlines():
            path = line[3:].strip()
            if " -> " in path:  # rename entry: 'old -> new' — the new path is what's edited
                path = path.split(" -> ", 1)[1].strip()
            path = path.strip('"')  # porcelain quotes paths containing special chars
            if path:
                files.add(path)
    return files


@pr_group.command(
    "triage",
    help="Ranked digest of all open agents/* PRs (ci + review + conflict + age) — review the highest-value, lowest-risk first.",
)
@click.option("--repo", "repo_opt", default=None)
@click.option("--json", "as_json", is_flag=True)
def pr_triage(repo_opt: str | None, as_json: bool) -> None:
    repo = _resolve_repo(repo_opt)
    if not _gh_ready():
        _emit(
            {
                "open": 0,
                "quick_merge": 0,
                "prs": [],
                "action": "gh unavailable — cannot triage open PRs",
            },
            as_json,
        )
        return
    out = _run(
        [
            "gh",
            "pr",
            "list",
            "--state",
            "open",
            "--search",
            "head:agents/",
            "--json",
            "number,headRefName,state,mergedAt,statusCheckRollup,isDraft,autoMergeRequest,"
            "reviewDecision,mergeable,createdAt",
            "--limit",
            "100",
        ],
        cwd=repo,
    )
    rows: list[dict] = []
    if out.returncode == 0:
        try:
            rows = json.loads(out.stdout or "[]")
        except json.JSONDecodeError:
            rows = []
    agent_rows = [r for r in rows if str(r.get("headRefName", "")).startswith("agents/")]
    entries = sorted(
        (_triage_entry(r) for r in agent_rows), key=lambda e: (e["rank"], e["created_at"])
    )
    quick = sum(1 for e in entries if e["category"] == "quick-merge")
    if not entries:
        _emit(
            {
                "open": 0,
                "quick_merge": 0,
                "prs": [],
                "action": "no open agent PRs — nothing to triage",
            },
            as_json,
        )
        return
    if as_json:
        _emit(
            {
                "open": len(entries),
                "quick_merge": quick,
                "prs": entries,
                "action": "review in listed order; quick-merge rows are green + conflict-free + no required review",
            },
            as_json,
        )
        return
    lines = [f"{len(entries)} open agent PR(s) — review in this order ({quick} safe quick-merge):"]
    for e in entries:
        flag = "  ✅ quick-merge" if e["category"] == "quick-merge" else ""
        lines.append(
            f"  #{e['number']} {e['branch']} — {e['category']} "
            f"(ci={e['ci_rollup']}, review_required={e['review_required']}, conflict={e['conflict']}){flag}"
        )
    lines.append(
        "Tip: to leave the hot path entirely, set autonomy_level=auto_merge with a required check "
        "(docs/playbooks/pr-mode-ci-economics.md)."
    )
    click.echo("\n".join(lines))


@pr_group.command(
    "conflicts",
    help="Advisory: which live peer agent branch also edits your files (early-warning before a land-time conflict).",
)
@click.option(
    "--branch", default=None, help="Target agent branch (default: the current worktree's HEAD)."
)
@click.option("--repo", "repo_opt", default=None)
@click.option("--json", "as_json", is_flag=True)
def pr_conflicts(branch: str | None, repo_opt: str | None, as_json: bool) -> None:
    repo = _resolve_repo(repo_opt)
    integration = _integration_branch(repo)
    worktrees = _agent_worktrees(repo)
    target = branch or _git_out(["rev-parse", "--abbrev-ref", "HEAD"], cwd=repo)
    if not target.startswith("agents/"):
        raise click.ClickException(
            "not on an agents/* branch — pass --branch <agents/...> or run from inside an agent worktree."
        )
    target_files = _changed_files(repo, target, integration, worktrees.get(target))
    overlaps: list[dict] = []
    for peer, peer_wt in sorted(worktrees.items()):
        if peer == target:
            continue
        shared = sorted(target_files & _changed_files(repo, peer, integration, peer_wt))
        if shared:
            overlaps.append({"branch": peer, "files": shared})
    # Advisory ONLY — overlap is a heads-up, never a block: two agents may legitimately
    # touch one file in different places; the rebase-at-submit + merge queue catch a
    # real conflict at land. Always exit 0.
    _emit(
        {
            "branch": target,
            "changed_files": len(target_files),
            "conflicts": overlaps
            if as_json
            else ("; ".join(f"{o['branch']}={','.join(o['files'])}" for o in overlaps) or "(none)"),
            "advisory": (
                "peer overlap — coordinate or expect a rebase at land"
                if overlaps
                else "no peer overlap"
            ),
        },
        as_json,
    )


def _rollup_state(pr: dict) -> str:
    # merged|red|queued|pending|review-required|passing|passing-unarmed|closed|none — one
    # CI signal distilled from gh's statusCheckRollup (+ a GraphQL mergeQueueEntry probe
    # injected by _pr_ci_rollup) for the autonomous driver loop.
    if pr.get("mergedAt") or str(pr.get("state", "")).upper() == "MERGED":
        return "merged"
    if str(pr.get("state", "")).upper() == "CLOSED":
        return "closed"
    checks = pr.get("statusCheckRollup") or []
    bad = {"FAILURE", "ERROR", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED", "STARTUP_FAILURE"}
    waiting = {"IN_PROGRESS", "QUEUED", "PENDING", "WAITING", "REQUESTED", "EXPECTED"}

    def fields(
        check: dict,
    ) -> set[str]:  # CheckRun uses conclusion/status; StatusContext uses state
        return {str(check.get(k) or "").upper() for k in ("conclusion", "status", "state")}

    if any(bad & fields(c) for c in checks):
        return "red"
    # Merge-queue membership (GraphQL mergeQueueEntry; gh pr view --json cannot supply it,
    # so _pr_ci_rollup injects it). A queued PR's merge_group checks read as `waiting`
    # below, so this MUST precede the waiting/no-checks arms — the driver waits on the
    # queue, never re-submits. UNMERGEABLE = the queue will eject it → red, so only this
    # PR is healed while followers keep merging. Absent entry → byte-unchanged (no queue).
    mq_state = str((pr.get("mergeQueueEntry") or {}).get("state") or "").upper()
    if mq_state == "UNMERGEABLE":
        return "red"
    if mq_state:  # QUEUED | AWAITING_CHECKS | MERGEABLE | LOCKED — in the queue, just wait
        return "queued"
    if not checks:
        return "pending"
    if any(waiting & fields(c) for c in checks):
        return "pending"
    # Green checks — but a required review (branch protection / ruleset / CODEOWNERS)
    # still blocks merge until a human approves. Distinct from passing-unarmed so the
    # driver STOPs for an approval instead of spinning on an auto-merge that has been
    # armed but can never fire while the review gate is open.
    if str(pr.get("reviewDecision") or "").upper() in {"REVIEW_REQUIRED", "CHANGES_REQUESTED"}:
        return "review-required"
    # Green — but only "passing" (auto-merge will land it) when auto-merge is armed
    # AND the PR isn't a draft; else "passing-unarmed" so the driver STOPs for a human
    # merge from the signal alone, never from a remembered submit merge_status.
    if pr.get("isDraft") or not pr.get("autoMergeRequest"):
        return "passing-unarmed"
    return "passing"


def _pr_ci_rollup(repo: str, branch: str) -> str:
    if not _gh_ready():
        return "unknown"
    out = _run(
        [
            "gh",
            "pr",
            "view",
            branch,
            "--json",
            "number,state,mergedAt,statusCheckRollup,isDraft,autoMergeRequest,reviewDecision",
        ],
        cwd=repo,
    )
    if out.returncode != 0:
        return "none"  # no PR for this branch (or gh error) → driver opens/submits
    try:
        pr = json.loads(out.stdout or "{}")
    except json.JSONDecodeError:
        return "unknown"
    if not pr:
        return "none"
    state = _rollup_state(pr)
    # A PR only enters the merge queue once green/running, so probe mergeQueueEntry only
    # for the non-final verdicts — a merged/closed/red/review-required result is already
    # authoritative, and skipping the probe there means a repo with NO merge queue makes
    # zero extra calls for them (byte-unchanged). _merge_queue_entry fails open to {}.
    if state in {"pending", "passing", "passing-unarmed"}:
        entry = _merge_queue_entry(repo, pr.get("number"))
        if entry:
            pr["mergeQueueEntry"] = entry
            return _rollup_state(pr)
    return state


def _merge_queue_entry(repo: str, number: int | None) -> dict:
    # gh pr view --json has no mergeQueueEntry field (gh 2.95), so read it via GraphQL —
    # gh resolves {owner}/{repo} from the repo's remote. Returns {} (not queued / no queue
    # configured / gh error) so _rollup_state stays byte-unchanged where no queue exists.
    if not number or not _gh_ready():
        return {}
    out = _run(
        [
            "gh",
            "api",
            "graphql",
            "-F",
            "owner={owner}",
            "-F",
            "name={repo}",
            "-F",
            f"number={int(number)}",
            "-f",
            "query=query($owner:String!,$name:String!,$number:Int!){"
            "repository(owner:$owner,name:$name){pullRequest(number:$number){"
            "mergeQueueEntry{state position}}}}",
        ],
        cwd=repo,
    )
    if out.returncode != 0:
        return {}
    try:
        data = json.loads(out.stdout or "{}")
    except json.JSONDecodeError:
        return {}
    pull = ((data.get("data") or {}).get("repository") or {}).get("pullRequest") or {}
    return pull.get("mergeQueueEntry") or {}


def _triage_entry(pr: dict) -> dict:
    # One ranked triage row for an open agents/* PR. Rank orders the human's
    # review queue to minimise time-to-unblock: safe quick-merges first (just
    # click merge), then the ones needing a real review, then conflict/red (need
    # work), then CI still running (no human action yet). created_at breaks ties
    # oldest-first so the backlog drains FIFO.
    rollup = _rollup_state(pr)  # already folds a blocking reviewDecision into "review-required"
    conflict = str(pr.get("mergeable") or "").upper() == "CONFLICTING"
    review_required = rollup == "review-required"
    green = rollup in ("passing", "passing-unarmed")
    if green and not conflict:
        category, rank = "quick-merge", 0  # green + clean + no required review → safe one-click
    elif review_required and not conflict:
        category, rank = "needs-review", 1
    elif conflict:
        category, rank = "conflict", 2  # needs a rebase before it can land
    elif rollup == "red":
        category, rank = "red", 3
    elif rollup in ("pending", "queued"):
        category, rank = "waiting", 4
    else:
        category, rank = rollup, 5
    return {
        "rank": rank,
        "category": category,
        "branch": pr.get("headRefName", ""),
        "number": pr.get("number"),
        "ci_rollup": rollup,
        "review_required": review_required,
        "conflict": conflict,
        "created_at": pr.get("createdAt", ""),
    }
