"""cos pr — pr-mode multi-agent git executor (TASK-517).

Thin, idempotent subcommands the agent drives from its OWN turn loop (never a
kernel daemon — hooks can't loop, MCP polling blocks the server):

    cos pr preflight   — capability check (remote + gh + required CI); degrade signal
    cos pr open        — isolate: claim/derive a session, create a worktree + agents/* branch
    cos pr submit      — publish: rebase onto FETCH_HEAD, sha-pinned lease push, PR, auto-merge
    cos pr status      — list this repo's pr-mode worktrees / branches / open PRs
    cos pr cleanup     — remove the worktree + delete the branch + prune

All gh-coupled code lives here in src/cli (P2/P8 — src/core stays agent/host
agnostic; it reaches every consumer via live symlinks). When a capability is
missing the executor degrades to the trunk publish path instead of failing
mid-loop. SPEC: docs/playbooks/pr-workflow.md.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

try:
    import fcntl
except ImportError:  # non-POSIX (Windows) — the reaper lock degrades to a no-op
    fcntl = None  # type: ignore[assignment]

import click

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


# --------------------------------------------------------------------------- #
# subprocess + git/gh helpers
# --------------------------------------------------------------------------- #
def _run(
    args: list[str], *, cwd: str | Path | None = None, timeout: int | None = None
) -> subprocess.CompletedProcess[str]:
    # Bound every gh/git call so a stalled network can never wedge the agent's
    # turn loop (the executor must stay non-blocking) — review finding 10.
    if timeout is None:
        try:
            timeout = max(1, int(os.environ.get("COS_PR_SUBPROCESS_TIMEOUT", "120")))
        except ValueError:
            timeout = 120
    try:
        return subprocess.run(
            args,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout if isinstance(exc.stdout, str) else ""
        return subprocess.CompletedProcess(
            args, returncode=124, stdout=out, stderr=f"timed out after {timeout}s"
        )


def _git(args: list[str], *, cwd: str | Path) -> subprocess.CompletedProcess[str]:
    return _run(["git", "-C", str(cwd), *args])


def _git_out(args: list[str], *, cwd: str | Path) -> str:
    proc = _git(args, cwd=cwd)
    return proc.stdout.strip() if proc.returncode == 0 else ""


def _commit_count(cwd: str | Path, rev_range: str) -> int:
    # 0 on any error (unresolved range) so the local-rung report fails toward
    # "nothing to integrate" rather than a crash.
    out = _git_out(["rev-list", "--count", rev_range], cwd=cwd)
    try:
        return int(out)
    except ValueError:
        return 0


def _toplevel(start: str | Path) -> str | None:
    proc = _run(["git", "-C", str(start), "rev-parse", "--show-toplevel"])
    return proc.stdout.strip() or None if proc.returncode == 0 else None


def _sanitize(token: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", token).strip("-") or "x"


def _repo_slug(repo_root: str) -> str:
    real = os.path.realpath(repo_root)
    digest = hashlib.sha256(real.encode()).hexdigest()[:8]
    return f"{_sanitize(Path(real).name)}-{digest}"


def _worktree_root(repo_root: str) -> Path:
    base = os.environ.get("COS_WORKTREE_ROOT") or str(Path.home() / ".coding-os" / "worktrees")
    return Path(base) / _repo_slug(repo_root)


def _main_repo_root(repo: str) -> str:
    # The main checkout owns the one hub-settings.json every worktree shares. A
    # linked worktree's --git-common-dir resolves (relative to the worktree) to
    # <main>/.git, whose parent is the main repo; the main checkout returns a bare
    # ".git" and the parent collapses to repo itself. SPEC: pr-workflow.md § 3.
    common = _git_out(["rev-parse", "--git-common-dir"], cwd=repo)
    if not common:
        return repo
    common_path = Path(common)
    if not common_path.is_absolute():
        common_path = (Path(repo) / common_path).resolve()
    return str(common_path.parent) if common_path.name == ".git" else repo


def _git_settings(repo: str) -> dict:
    # Self-read the consumer's git_settings: cos-env.sh exports COS_GIT_* only into
    # hook subprocesses, so the agent's `cos pr` shell has none — without this the
    # configured rung/branch is silently ignored. Best-effort: any read error falls
    # through to the env/default in the callers below.
    settings_path = Path(_main_repo_root(repo)) / ".coding-os" / "hub-settings.json"
    if not settings_path.exists():
        return {}
    try:
        raw = json.loads(settings_path.read_text())
    except Exception:
        return {}
    section = raw.get("git_settings")
    return section if isinstance(section, dict) else {}


def _integration_branch(repo: str | None = None) -> str:
    # Explicit env var always wins; else the consumer's saved integration_branch.
    env = os.environ.get("COS_GIT_INTEGRATION_BRANCH")
    if env:
        return env
    if repo is not None:
        branch = _git_settings(repo).get("integration_branch")
        if isinstance(branch, str) and branch:
            return branch
    return "main"


_AUTONOMY_LEVELS = ("local", "draft", "auto_merge", "autonomous")


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


def _agent_session() -> str:
    try:
        from cli.board_commands import _agent_session_id

        sid = _agent_session_id()
    except Exception:  # board_os optional — never break `cos pr` on its absence
        sid = None
    sid = sid or os.environ.get("COS_AGENT_SESSION_ID") or os.environ.get("COS_PANEL_ID")
    # Unique per process when no session id resolves — a shared constant would
    # collide branches/worktrees across concurrent agents (review finding 6).
    return _sanitize(sid) if sid else f"pid-{os.getpid()}"


# --------------------------------------------------------------------------- #
# capability preflight
# --------------------------------------------------------------------------- #
def _has_remote(repo: str) -> bool:
    return bool(_git_out(["remote"], cwd=repo))


def _gh_ready() -> bool:
    from shutil import which

    if which("gh") is None:
        return False
    return _run(["gh", "auth", "status"]).returncode == 0


def _has_required_check(repo: str, integration: str) -> bool:
    # precondition for safely arming auto-merge; best-effort, False on any doubt
    if not _gh_ready():
        return False
    slug = _git_out(["config", "--get", "remote.origin.url"], cwd=repo)
    if not slug:
        return False
    # cwd=repo so gh resolves the {owner}/{repo} placeholder from THIS repo's remote,
    # not the process cwd — a submit run from another checkout would else probe the
    # wrong repo's branch protection (D4). Every sibling gh call already scopes cwd.
    proc = _run(
        ["gh", "api", f"repos/{{owner}}/{{repo}}/branches/{integration}/protection/required_status_checks"],
        cwd=repo,
    )
    return proc.returncode == 0


def _unprotected_warning(integration: str) -> str:
    return (
        f"unprotected integration branch '{integration}': no GitHub branch protection / required "
        f"check detected — the client-side branch-guard is the ONLY barrier, and any human, GUI, "
        f"or hook-bypassed agent can push directly to '{integration}'. Set up a GitHub ruleset "
        f"(require a PR + required status checks + block direct pushes) so the server enforces the "
        f"wall (pr-workflow.md §11)."
    )


def _preflight(repo: str, integration: str) -> dict:
    remote = _has_remote(repo)
    gh = _gh_ready()
    required = _has_required_check(repo, integration) if (remote and gh) else False
    # A reachable forge with no required check = the integration branch has no server-side
    # wall, so the client branch-guard is the only barrier (the Layer-0 legibility gap).
    unprotected_integration = remote and not required
    missing = [
        name
        for name, present in (("remote", remote), ("gh", gh), ("required-ci", required))
        if not present
    ]
    return {
        "remote": remote,
        "gh": gh,
        "required_check": required,
        "pr_ok": remote and gh,
        "unprotected_integration": unprotected_integration,
        "missing": missing,
    }


def _branches(repo: str) -> list[str]:
    # Local heads + origin remotes, de-duplicated to bare names — the source for
    # the Hub branch dropdowns so a consumer can't pick a non-existent branch.
    raw = _git_out(
        ["for-each-ref", "--format=%(refname:short)", "refs/heads", "refs/remotes/origin"],
        cwd=repo,
    )
    names: set[str] = set()
    for line in raw.splitlines():
        name = line.strip()
        if not name or name.endswith("/HEAD") or name == "origin":
            continue
        names.add(name[len("origin/"):] if name.startswith("origin/") else name)
    return sorted(names)


def _git_state(repo: str) -> dict:
    # Real repo state for the Config Git tab (TASK-534) — local git only, so it
    # answers even when gh/remote are down (the capability probe degrades alone).
    return {
        "branches": _branches(repo),
        "current_branch": _git_out(["rev-parse", "--abbrev-ref", "HEAD"], cwd=repo),
        "remote_url": _git_out(["config", "--get", "remote.origin.url"], cwd=repo),
    }


def _emit(payload: dict, as_json: bool) -> None:
    if as_json:
        click.echo(json.dumps(payload, indent=2))
        return
    for key, value in payload.items():
        click.echo(f"{key}: {value}")


# --------------------------------------------------------------------------- #
# worktree resolution
# --------------------------------------------------------------------------- #
def _claim_task() -> str | None:
    try:
        from cli.board_commands import _agent_session_id, _db_conn
        from core.board_os.mcp_tools import cos_task_claim_next
    except Exception:
        return None
    try:
        conn = _db_conn()
        env = json.loads(cos_task_claim_next(conn, agent_session=_agent_session_id()))
    except Exception:
        return None
    claimed = (env.get("data") or {}).get("claimed") if env.get("ok") else None
    return claimed.get("id") if claimed else None


def _branch_for(task_slug: str, session: str) -> str:
    return f"agents/{task_slug}/{session}"


def _resolve_worktree(repo: str, task_slug: str, session: str) -> tuple[Path, str]:
    # Find the worktree+branch `open` created, even when the session id differs
    # across processes (the pid-<getpid> fallback gives a fresh value per process,
    # TASK-541). Fast path: the session-derived path exists. Else scan this repo's
    # worktree root for the task slug and read the real branch off the single match
    # (the reaper derives it the same way); ambiguous/none falls back to the
    # computed pair so the caller's existence check still surfaces a clear error.
    root = _worktree_root(repo)
    computed = root / f"{task_slug}-{session}"
    if (computed / ".git").exists():
        return computed, _branch_for(task_slug, session)
    candidates = (
        sorted(p for p in root.glob(f"{task_slug}-*") if (p / ".git").exists())
        if root.exists()
        else []
    )
    if len(candidates) == 1:
        wt = candidates[0]
        return wt, _git_out(["rev-parse", "--abbrev-ref", "HEAD"], cwd=wt) or _branch_for(task_slug, session)
    return computed, _branch_for(task_slug, session)


def _resolve_repo(repo_opt: str | None) -> str:
    repo = _toplevel(repo_opt or os.getcwd())
    if repo is None:
        raise click.ClickException(
            "not inside a git repository — cos pr needs a git checkout (run 'git init' first)."
        )
    return repo


# --------------------------------------------------------------------------- #
# commands
# --------------------------------------------------------------------------- #
@click.group("pr", help="pr-mode multi-agent git executor (worktree → PR → CI → merge → cleanup).")
def pr_group() -> None:
    pass


@pr_group.command("preflight", help="Check pr-mode capability (remote + gh + required CI).")
@click.option("--repo", "repo_opt", default=None, help="Repo path (default: cwd).")
@click.option("--integration", default=None, help="Integration branch (default: COS_GIT_INTEGRATION_BRANCH or main).")
@click.option("--json", "as_json", is_flag=True, help="Emit JSON.")
def pr_preflight(repo_opt: str | None, integration: str | None, as_json: bool) -> None:
    repo = _resolve_repo(repo_opt)
    integration = integration or _integration_branch(repo)
    cap = _preflight(repo, integration)
    payload = {**cap, "mode": "pr" if cap["pr_ok"] else "degraded-trunk"}
    if cap["unprotected_integration"]:
        payload["warning"] = _unprotected_warning(integration)
    _emit(payload, as_json)
    sys.exit(0 if cap["pr_ok"] else 1)


@pr_group.command("open", help="Isolate work in a worktree + agents/* branch.")
@click.option("--task", "task_id", default=None, help="Board task id (else claim the next ready task).")
@click.option("--adhoc", is_flag=True, help="No board task — isolate ad-hoc code work.")
@click.option("--repo", "repo_opt", default=None)
@click.option("--integration", default=None)
@click.option("--json", "as_json", is_flag=True)
def pr_open(
    task_id: str | None, adhoc: bool, repo_opt: str | None, integration: str | None, as_json: bool
) -> None:
    repo = _resolve_repo(repo_opt)
    integration = integration or _integration_branch(repo)
    session = _agent_session()

    if adhoc:
        task_slug, task_id = "adhoc", None
    elif task_id:
        task_slug = _sanitize(task_id)
    else:
        task_id = _claim_task()
        if not task_id:
            raise click.ClickException(
                "no runnable task to claim — pass --task <id>, or --adhoc for no-task work."
            )
        task_slug = _sanitize(task_id)

    branch = _branch_for(task_slug, session)
    wt = _worktree_root(repo) / f"{task_slug}-{session}"
    cap = _preflight(repo, integration)

    if cap["remote"]:
        _git(["fetch", "origin", integration], cwd=repo)

    already = wt.exists() and (wt / ".git").exists()
    if not already:
        wt.parent.mkdir(parents=True, exist_ok=True)
        base = f"origin/{integration}" if cap["remote"] else integration
        add = _git(["worktree", "add", "-b", branch, str(wt), base], cwd=repo)
        if add.returncode != 0:
            # Branch already exists (idempotent re-open) — attach it instead.
            attach = _git(["worktree", "add", str(wt), branch], cwd=repo)
            if attach.returncode != 0:
                raise click.ClickException(
                    f"worktree add failed:\n{add.stderr.strip()}\n{attach.stderr.strip()}"
                )
    # Shared objects/refs/packed-refs across worktrees → background gc during a
    # peer's rebase is unsafe. Pin it off per worktree.
    _git(["config", "gc.auto", "0"], cwd=wt)
    # Lock the worktree so a peer's `git worktree prune` cannot remove a live
    # session's checkout (TASK-519 §2). Idempotent — a re-lock just errors.
    _git(["worktree", "lock", str(wt), "--reason", f"pr-mode session {session}"], cwd=repo)

    _emit(
        {
            "worktree": str(wt),
            "branch": branch,
            "task": task_id or "(adhoc)",
            "integration": integration,
            "project_root": repo,
            "mode": "pr" if cap["pr_ok"] else "degraded-trunk",
            "missing": ",".join(cap["missing"]) or "(none)",
            "next": f"export COS_PROJECT_ROOT={repo}  # then edit inside {wt}",
        },
        as_json,
    )


@pr_group.command("submit", help="Publish: rebase onto FETCH_HEAD, lease-push, open PR, arm auto-merge.")
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

    # `local` rung (TASK-540): commit-only, never push. Short-circuits before the
    # capability probe so a repo with no remote is the intended mode, not a degrade.
    autonomy = _autonomy_level(repo)
    if autonomy == "local":
        ahead = _commit_count(wt, f"{integration}..{branch}")
        behind = _commit_count(wt, f"{branch}..{integration}")
        if ahead == 0:
            action = (
                f"no commits to integrate yet — commit your work in {wt}, then re-run 'cos pr submit'."
            )
        else:
            stale = f" branch is {behind} behind '{integration}' — rebase before integrating." if behind else ""
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
    # so a red / quota-dead CI (TASK-513) can't grow open PRs without bound, and
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
    lease = f"--force-with-lease={branch}:{remote_sha}" if remote_sha else f"--force-with-lease={branch}"
    push = _git(["push", lease, "--force-if-includes", "-u", "origin", branch], cwd=wt)
    if push.returncode != 0:
        raise click.ClickException(f"push rejected (lease/connectivity):\n{push.stderr.strip()}")

    pr = _run(
        [
            "gh", "pr", "create", "--base", integration, "--head", branch,
            "--title", title or branch, "--body", body or f"agent branch {branch}",
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

    # A no-required-check repo silently no-ops `gh pr merge --auto`; surface the
    # outcome so submit never strands an open PR with no signal (TASK-527).
    if armed:
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
        action = "required check exists but 'gh pr merge --auto' did not arm — check gh auth/permissions"

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
        "autonomy_level": autonomy,
        "merge_status": merge_status,
        "board_blocked": board_blocked,
        "action": action,
    }
    if cap["unprotected_integration"]:
        payload["warning"] = _unprotected_warning(integration)
    _emit(payload, as_json)


@pr_group.command("status", help="List this repo's pr-mode worktrees, branches, and open PRs.")
@click.option("--repo", "repo_opt", default=None)
@click.option("--branch", default=None, help="Report one agent branch's CI rollup (merged|red|pending|passing|passing-unarmed|closed|none) — the driver-loop signal.")
@click.option("--json", "as_json", is_flag=True)
def pr_status(repo_opt: str | None, branch: str | None, as_json: bool) -> None:
    repo = _resolve_repo(repo_opt)
    if branch:
        # Single-branch CI signal the pr-mode-driver skill branches on (TASK-529).
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
            ["gh", "pr", "list", "--search", "head:agents/", "--json",
             "number,headRefName,state,mergedAt,statusCheckRollup,isDraft,autoMergeRequest"],
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
            cur = line[len("worktree "):].strip()
        elif line.startswith("branch ") and cur:
            name = _unqualify_head(line[len("branch "):].strip())
            if name.startswith("agents/"):
                result[name] = Path(cur)
    return result


def _unqualify_head(ref: str) -> str:
    return ref[len("refs/heads/"):] if ref.startswith("refs/heads/") else ref


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


@pr_group.command("conflicts", help="Advisory: which live peer agent branch also edits your files (early-warning before a land-time conflict).")
@click.option("--branch", default=None, help="Target agent branch (default: the current worktree's HEAD).")
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


def _pr_state(repo: str, branch: str) -> str:
    # "merged" | "closed" | "open" | "none" | "unknown" — drives the cleanup
    # merge-gate so an open PR's worktree isn't destroyed mid-flight (TASK-530).
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


def _rollup_state(pr: dict) -> str:
    # merged|red|pending|passing|passing-unarmed|closed|none — one CI signal
    # distilled from gh's statusCheckRollup for the autonomous driver loop (TASK-529).
    if pr.get("mergedAt") or str(pr.get("state", "")).upper() == "MERGED":
        return "merged"
    if str(pr.get("state", "")).upper() == "CLOSED":
        return "closed"
    checks = pr.get("statusCheckRollup") or []
    if not checks:
        return "pending"
    bad = {"FAILURE", "ERROR", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED", "STARTUP_FAILURE"}
    waiting = {"IN_PROGRESS", "QUEUED", "PENDING", "WAITING", "REQUESTED", "EXPECTED"}

    def fields(check: dict) -> set[str]:  # CheckRun uses conclusion/status; StatusContext uses state
        return {str(check.get(k) or "").upper() for k in ("conclusion", "status", "state")}

    if any(bad & fields(c) for c in checks):
        return "red"
    if any(waiting & fields(c) for c in checks):
        return "pending"
    # Green — but only "passing" (auto-merge will land it) when auto-merge is armed
    # AND the PR isn't a draft; else "passing-unarmed" so the driver STOPs for a human
    # merge from the signal alone, never from a remembered submit merge_status (D5).
    if pr.get("isDraft") or not pr.get("autoMergeRequest"):
        return "passing-unarmed"
    return "passing"


def _pr_ci_rollup(repo: str, branch: str) -> str:
    if not _gh_ready():
        return "unknown"
    out = _run(
        ["gh", "pr", "view", branch, "--json",
         "state,mergedAt,statusCheckRollup,isDraft,autoMergeRequest"],
        cwd=repo,
    )
    if out.returncode != 0:
        return "none"  # no PR for this branch (or gh error) → driver opens/submits
    try:
        pr = json.loads(out.stdout or "{}")
    except json.JSONDecodeError:
        return "unknown"
    return _rollup_state(pr) if pr else "none"


def _branch_recoverable(repo: str, branch: str, integration: str) -> bool:
    # gh-independent cleanup safety net: True when every branch commit is already
    # reachable from an origin ref (or the local integration), so deleting the
    # local branch loses nothing (TASK-530).
    if not _git_out(["rev-parse", "--verify", branch], cwd=repo):
        return True
    if _git(["merge-base", "--is-ancestor", branch, integration], cwd=repo).returncode == 0:
        return True
    for ref in (f"origin/{branch}", f"origin/{integration}"):
        if _git(["merge-base", "--is-ancestor", branch, ref], cwd=repo).returncode == 0:
            return True
    return False


def _preserve_reaped(repo: str, wt: Path, branch: str) -> str | None:
    # gh-independent, offline-safe preservation before a reap destroys anything
    # (TASK-535). Commit any uncommitted/untracked work onto the (doomed) branch —
    # the worktree + branch are about to be GC'd, so mutating them is free, and
    # `--no-verify` guarantees the capture can't be blocked by a consumer hook
    # (a plain `git stash create` would silently drop untracked files, which is
    # exactly the new files an agent creates). Then bundle the branch tip into a
    # quarantine dir. Returns the bundle path, or None when the work could not be
    # safely captured (commit or bundle failed) — the caller then keeps the worktree.
    if _git_out(["status", "--porcelain"], cwd=wt):
        _git(["add", "-A"], cwd=wt)
        # Inject a fallback identity so an un-configured worktree (no user.email/name)
        # still commits — else the dirty work never reaches the branch and the bundle
        # below would silently capture only the old tip (D2). Bail on any other commit
        # failure too, so the caller never treats unpreserved work as safe.
        commit = _git(
            ["-c", "user.email=reaper@coding-os", "-c", "user.name=cos-reaper",
             "commit", "-q", "--no-verify", "-m", f"chore: preserve reaped agent work ({branch})"],
            cwd=wt,
        )
        if commit.returncode != 0:
            return None
    base = os.environ.get("COS_REAPED_ROOT") or str(Path.home() / ".coding-os" / "reaped")
    qdir = Path(base) / _repo_slug(repo)
    qdir.mkdir(parents=True, exist_ok=True)
    bundle = qdir / f"{_sanitize(branch)}-{int(time.time())}.bundle"
    ok = _git(["bundle", "create", str(bundle), branch], cwd=repo).returncode == 0
    return str(bundle) if ok else None


@pr_group.command("cleanup", help="Remove the worktree + delete the branch + prune (merge-gated; --force to override).")
@click.option("--task", "task_id", default=None)
@click.option("--adhoc", is_flag=True)
@click.option("--repo", "repo_opt", default=None)
@click.option("--force", is_flag=True, help="Remove even if the PR is open / the branch is unpushed (human override).")
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

    # Merge-gate (TASK-530): only destroy the worktree+branch once work has landed
    # (merged/closed) or is fully on origin; --force is the human override.
    if not force:
        # Ownership gate (review finding 2): under session drift the single-candidate
        # fallback in _resolve_worktree can resolve a live PEER's worktree (same task
        # slug, different session) — destroying it would wipe active peer work. Refuse
        # only when the owner session is provably LIVE; a drifted-gone ("unknown") or
        # dead ("offline") owner still cleans up, preserving the TASK-541 drift path.
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
        # Preserve-before-destroy net (TASK-566 H): for any OTHER state (merged/closed)
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


# --------------------------------------------------------------------------- #
# orphan reaper (TASK-519) — owner-independent GC keyed on presence-offline.
# A crashed agent never cleans up after itself (the exact Rule-21 failure mode),
# so an out-of-band sweep does it. SPEC: docs/playbooks/pr-workflow.md § 7.
# --------------------------------------------------------------------------- #
def _session_state(session: str, repo: str) -> str:
    # Three-state liveness, reaped only on POSITIVE death evidence: "offline"
    # (>=1 record, ALL proving death — ended_at set, or a SAME-HOST recorded pid no
    # longer alive), "live" (a record whose owner could still be working),
    # "unknown" (no matching record). session_presence()=="offline" is NOT the
    # death oracle: it also fires for a PID-alive agent merely idle >30min (a long
    # build or model turn), and reaping that destroys live uncommitted work
    # (finding 1). The reaper reaps "offline" outright and "unknown" only when the
    # worktree is also stale-by-age (finding 2).
    try:
        from core.board_os.presence import pid_alive
    except Exception:
        return "unknown"  # presence module absent → never positively offline
    this_host = socket.gethostname()
    state_dir = Path(repo) / ".coding-os"
    saw_dead = False
    for sess_dir in state_dir.glob("*/sessions"):
        jf = sess_dir / f"{session}.json"
        if not jf.is_file():
            continue
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue  # unreadable (e.g. mid-write) → not proof of death; keep checking
        pid = int(data.get("pid") or 0)
        # pid_alive is host-local: a foreign-host pid happening to be free here is
        # NOT death (L5). Trust it only same-host; legacy records (no host) default
        # to this host so pre-upgrade orphans still reap. ended_at is host-agnostic.
        host = data.get("host") or this_host
        same_host = host == this_host
        dead = data.get("ended_at") is not None or (same_host and pid > 0 and not pid_alive(pid))
        if not dead:
            return "live"  # alive owner (or no same-host death proof) → keep, fail-safe
        saw_dead = True
    return "offline" if saw_dead else "unknown"


def _worktree_stale(wt: Path) -> bool:
    # A no-presence-record orphan is reapable only once its worktree has been idle
    # past COS_PR_ORPHAN_MAX_AGE (default 24h), measured by the NEWEST file mtime
    # anywhere in the tree (excluding .git) — NOT the top-level dir mtime, which
    # never moves when a live agent edits nested files like src/** (finding 2), so
    # using it would reap a long-running agent's worktree mid-edit. Stops early on
    # the first fresh file, so a live worktree costs only a shallow walk.
    max_age = _env_int("COS_PR_ORPHAN_MAX_AGE", 86400)
    cutoff = time.time() - max_age
    try:
        newest = wt.stat().st_mtime
    except OSError:
        return False  # can't determine age → keep (fail safe)
    if newest > cutoff:
        return False
    for root, dirs, files in os.walk(wt):
        if ".git" in dirs:
            dirs.remove(".git")
        for name in files:
            if name == ".git":
                continue  # linked-worktree .git pointer — creation metadata, not activity
            try:
                mtime = (Path(root) / name).stat().st_mtime
            except OSError:
                continue
            if mtime > cutoff:
                return False  # fresh activity anywhere → not stale
            if mtime > newest:
                newest = mtime
    return (time.time() - newest) > max_age


def _ledger_path(repo: str) -> Path:
    return Path(repo) / ".coding-os" / ".pr-cleanup-ledger.json"


def _ledger_load(repo: str) -> list[dict]:
    path = _ledger_path(repo)
    if not path.is_file():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8")) or []
    except (OSError, json.JSONDecodeError):
        return []


def _ledger_save(repo: str, entries: list[dict]) -> None:
    path = _ledger_path(repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    # pid-unique tmp so two concurrent writers can't replace() a name the other
    # already renamed away (mirrors presence_write.py).
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(entries, indent=2), encoding="utf-8")
    tmp.replace(path)  # atomic record-verify: the rename is the commit point


def _ledger_record(repo: str, branch: str, remote_pending: bool, pr_pending: bool) -> None:
    entries = [e for e in _ledger_load(repo) if e.get("branch") != branch]
    entries.append({"branch": branch, "remote_pending": remote_pending, "pr_pending": pr_pending})
    _ledger_save(repo, entries)


def _drain_ledger(repo: str) -> list[str]:
    # Retry the network-bound steps (remote delete + PR close) for entries an
    # offline/partial reap could not finish; drop the ones that now complete.
    entries = _ledger_load(repo)
    if not entries:
        return []
    drained: list[str] = []
    kept: list[dict] = []
    for entry in entries:
        branch = entry.get("branch")
        if not branch:
            continue  # malformed/legacy entry — skip rather than abort the drain
        remote_pending = entry.get("remote_pending", False)
        pr_pending = entry.get("pr_pending", False)
        if remote_pending and _has_remote(repo):
            remote_pending = _git(["push", "origin", "--delete", branch], cwd=repo).returncode != 0
        if pr_pending and _gh_ready():
            pr_pending = not _pr_close(repo, branch)
        if not remote_pending and not pr_pending:
            drained.append(branch)
        else:
            kept.append({"branch": branch, "remote_pending": remote_pending, "pr_pending": pr_pending})
    _ledger_save(repo, kept)
    return drained


def _pr_close(repo: str, branch: str) -> bool:
    # True when the branch has no open PR (already drained) or the close succeeds
    # — so a branch that never had a PR can't churn the ledger forever (finding 11).
    listing = _run(
        ["gh", "pr", "list", "--head", branch, "--state", "open", "--json", "number"], cwd=repo
    )
    if listing.returncode != 0:
        return False  # couldn't list (timeout/error) → keep the ledger entry, retry later
    try:
        has_open = bool(json.loads(listing.stdout or "[]"))
    except json.JSONDecodeError:
        has_open = True  # unparseable listing → assume a PR may exist and try to close
    if not has_open:
        return True
    return _run(["gh", "pr", "close", branch], cwd=repo).returncode == 0


def _reap_one(repo: str, wt: Path, branch: str) -> dict:
    # The worktree is a re-creatable checkout; the branch commits + uncommitted changes
    # are the WORK and must survive (TASK-535). So: preserve whenever the branch is not
    # already on origin/integration OR the tree is dirty, and GC the worktree + delete
    # the branch ONLY once the work is safe — on a remote ref, or a confirmed bundle.
    # If preservation fails, keep BOTH the worktree and the branch (D2).
    integration = _integration_branch(repo)
    recoverable = _branch_recoverable(repo, branch, integration)
    dirty = bool(_git_out(["status", "--porcelain"], cwd=wt))
    preserved = _preserve_reaped(repo, wt, branch) if (not recoverable or dirty) else None
    # Dirty uncommitted work is safe only if preservation captured it (it commits the
    # dirty tree onto the branch, then bundles) — `recoverable` alone covers only the
    # COMMITTED branch, so recoverable+dirty+preserve-failed must NOT count as safe (D2).
    work_safe = (recoverable and not dirty) or preserved is not None

    _git(["worktree", "unlock", str(wt)], cwd=repo)  # offline worktrees may be locked
    # Destroy the worktree ONLY once the work is safe (on a remote/integration ref or
    # bundled). When preservation failed, the worktree may hold the only copy of the
    # reaped work — keep it AND the branch for manual recovery, flagged needs_attention
    # (D2). A later sweep retries preservation and removes it once it succeeds.
    local = remote_pending = pr_pending = removed = False
    if work_safe:
        removed = _git(["worktree", "remove", "--force", str(wt)], cwd=repo).returncode == 0
        local = _git(["branch", "-D", branch], cwd=repo).returncode == 0
        if _has_remote(repo):
            remote_pending = _git(["push", "origin", "--delete", branch], cwd=repo).returncode != 0
        pr_pending = _gh_ready() and not _pr_close(repo, branch)
    _git(["worktree", "prune"], cwd=repo)
    _heal_budget_clear(repo, branch)  # owner is gone — drop its heal budget (finding 8)
    if remote_pending or pr_pending:
        _ledger_record(repo, branch, remote_pending, pr_pending)  # drains on next online sweep
    return {
        "worktree": str(wt),
        "branch": branch,
        "worktree_removed": removed,
        "local_deleted": local,
        "remote_pending": remote_pending,
        "pr_pending": pr_pending,
        "recoverable": recoverable,
        "preserved": preserved,
        "needs_attention": not work_safe,  # branch kept: not on origin AND bundle failed
    }


@pr_group.command("reap", help="GC worktrees/branches/PRs of presence-offline sessions; drain the cleanup ledger.")
@click.option("--repo", "repo_opt", default=None)
@click.option("--dry-run", is_flag=True, help="Report what would be reaped; change nothing.")
@click.option("--json", "as_json", is_flag=True)
def pr_reap(repo_opt: str | None, dry_run: bool, as_json: bool) -> None:
    repo = _resolve_repo(repo_opt)
    # One reaper per repo at a time — pr-reap.sh backgrounds this on EVERY
    # SessionStart, so N concurrent sessions would otherwise double-GC the same
    # orphan and clobber each other's ledger writes (finding 2). A peer holding
    # the lock already covers this repo, so we bow out cleanly.
    # Closing the fd on context exit releases the flock.
    lock_path = Path(repo) / ".coding-os" / ".pr-reap.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "w", encoding="utf-8") as lock_fd:
        if fcntl is not None:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                _emit(
                    {"reaped": 0, "kept_live": 0, "ledger_drained": "(skipped: reaper already running)"},
                    as_json,
                )
                return
        wt_root = _worktree_root(repo)
        drained = [] if dry_run else _drain_ledger(repo)
        reaped: list[dict] = []
        kept: list[dict] = []
        if wt_root.is_dir():
            for wt in sorted(p for p in wt_root.iterdir() if p.is_dir()):
                branch = _git_out(["rev-parse", "--abbrev-ref", "HEAD"], cwd=wt)
                if not branch.startswith("agents/"):
                    continue
                session = branch.rsplit("/", 1)[-1]
                state = _session_state(session, repo)
                reapable = state == "offline" or (state == "unknown" and _worktree_stale(wt))
                if reapable:
                    reaped.append(
                        {"worktree": str(wt), "branch": branch, "would_reap": True}
                        if dry_run
                        else _reap_one(repo, wt, branch)
                    )
                else:
                    if not dry_run:
                        # Re-assert the lock so a peer's prune can't drop a live checkout (§2).
                        _git(["worktree", "lock", str(wt), "--reason", "pr-mode live session"], cwd=repo)
                    kept.append({"worktree": str(wt), "branch": branch, "live": True})
        _emit(
            {
                "reaped": len(reaped),
                "kept_live": len(kept),
                "ledger_drained": ",".join(drained) or "(none)",
                "detail": reaped if as_json else f"{len(reaped)} reaped",
            },
            as_json,
        )


# --------------------------------------------------------------------------- #
# bounded self-heal + autonomy circuit-breaker (TASK-520) — the autonomous loop
# can never burn unbounded tokens / CI-quota. SPEC: docs/playbooks/pr-workflow.md § 8.
# --------------------------------------------------------------------------- #
def _heal_budget_path(repo: str) -> Path:
    return Path(repo) / ".coding-os" / ".pr-heal-budget.json"


@contextlib.contextmanager
def _heal_lock(repo: str):
    # Serialize the heal-budget read-modify-write so concurrent agents can't clobber
    # each other's counts (L4). DEDICATED lock file — never .pr-reap.lock — because
    # _reap_one runs under the reap flock and calls _heal_budget_clear; reusing the
    # reap lock would re-enter and deadlock. Degrades to a no-op on Windows (fcntl
    # None); the lost-update there is acceptable (heal counts are advisory).
    if fcntl is None:
        yield
        return
    lock_path = Path(repo) / ".coding-os" / ".pr-heal.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "w", encoding="utf-8") as lock_fd:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        yield


def _heal_budget(repo: str) -> dict:
    path = _heal_budget_path(repo)
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8")) or {}
    except (OSError, json.JSONDecodeError):
        return {}


def _heal_budget_save(repo: str, data: dict) -> None:
    path = _heal_budget_path(repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    # pid-unique tmp — a process-shared name races on replace() (mirrors
    # presence_write.py).
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(path)


def _heal_budget_clear(repo: str, branch: str) -> None:
    # Drop a branch's heal count on success/cleanup so a later re-open is never
    # pre-escalated by a stale count and the file can't grow unbounded (finding 8).
    with _heal_lock(repo):
        budget = _heal_budget(repo)
        if branch in budget:
            del budget[branch]
            _heal_budget_save(repo, budget)


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, str(default))))
    except ValueError:
        return default


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
        ["gh", "pr", "list", "--search", "head:agents/", "--state", "open", "--json", "headRefName"],
        cwd=repo,
    )
    if proc.returncode != 0:
        return -1
    try:
        prs = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        return -1
    return sum(1 for p in prs if str(p.get("headRefName", "")).rsplit("/", 1)[-1] == session)


def _escalate_blocked(repo: str, task_id: str | None, summary: str, move_reason: str) -> bool:
    # Generic "move the board task to blocked + log why" — callers own the wording
    # (heal: budget exhausted; submit: auto-merge deadlock) so the work-log line is
    # accurate per cause rather than always reading "self-heal".
    if not task_id:
        return False
    try:
        from cli.board_commands import _agent_session_id, _db_conn
        from core.board_os.mcp_tools import cos_task_move, cos_work_log_append

        conn = _db_conn()
        cos_work_log_append(conn, task_id=task_id, summary=summary)
        env = json.loads(
            cos_task_move(
                conn,
                task_id=task_id,
                to="blocked",
                reason=move_reason,
                agent_session=_agent_session_id(),
            )
        )
        return bool(env.get("ok"))
    except Exception:
        return False  # no board / unavailable → escalation signal still returned to caller


@pr_group.command("heal", help="Record a self-heal attempt on a red PR; escalate to blocked when the budget is spent.")
@click.option("--task", "task_id", default=None)
@click.option("--adhoc", is_flag=True)
@click.option("--repo", "repo_opt", default=None)
@click.option("--reason", default="CI red", help="Failure summary recorded on escalation.")
@click.option("--json", "as_json", is_flag=True)
def pr_heal(
    task_id: str | None, adhoc: bool, repo_opt: str | None, reason: str, as_json: bool
) -> None:
    repo = _resolve_repo(repo_opt)
    session = _agent_session()
    task_slug = "adhoc" if adhoc else _sanitize(task_id) if task_id else None
    if task_slug is None:
        raise click.ClickException("cos pr heal needs --task <id> or --adhoc.")
    branch = _branch_for(task_slug, session)
    # Read-modify-write under the dedicated heal flock so concurrent agents can't
    # clobber the count (L4).
    with _heal_lock(repo):
        budget = _heal_budget(repo)
        count = int(budget.get(branch, 0)) + 1
        budget[branch] = count
        _heal_budget_save(repo, budget)
    max_n = _env_int("COS_PR_HEAL_MAX", 3)

    if count > max_n:
        blocked = _escalate_blocked(
            repo,
            task_id,
            f"pr-mode self-heal budget exhausted after {count} attempts: {reason}",
            f"pr-mode heal budget exhausted ({reason})",
        )
        _emit(
            {
                "branch": branch,
                "attempt": count,
                "max": max_n,
                "escalated": True,
                "board_blocked": blocked,
                "action": "STOP re-pushing — task escalated to blocked",
            },
            as_json,
        )
        sys.exit(2)
    _emit(
        {
            "branch": branch,
            "attempt": count,
            "max": max_n,
            "escalated": False,
            "action": f"heal attempt {count}/{max_n} — fix and re-push",
        },
        as_json,
    )
