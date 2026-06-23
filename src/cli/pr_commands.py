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

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import click

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


# --------------------------------------------------------------------------- #
# subprocess + git/gh helpers
# --------------------------------------------------------------------------- #
def _run(args: list[str], *, cwd: str | Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args, cwd=str(cwd) if cwd else None, capture_output=True, text=True, check=False
    )


def _git(args: list[str], *, cwd: str | Path) -> subprocess.CompletedProcess[str]:
    return _run(["git", "-C", str(cwd), *args])


def _git_out(args: list[str], *, cwd: str | Path) -> str:
    proc = _git(args, cwd=cwd)
    return proc.stdout.strip() if proc.returncode == 0 else ""


def _toplevel(start: str | Path) -> str | None:
    proc = _run(["git", "-C", str(start), "rev-parse", "--show-toplevel"])
    return proc.stdout.strip() or None if proc.returncode == 0 else None


def _sanitize(token: str) -> str:
    """Branch/path-safe token (keep [A-Za-z0-9._-], collapse the rest to '-')."""
    return re.sub(r"[^A-Za-z0-9._-]+", "-", token).strip("-") or "x"


def _repo_slug(repo_root: str) -> str:
    """`<basename>-<sha8(realpath)>` — readable AND collision-free per checkout."""
    real = os.path.realpath(repo_root)
    digest = hashlib.sha256(real.encode()).hexdigest()[:8]
    return f"{_sanitize(Path(real).name)}-{digest}"


def _worktree_root(repo_root: str) -> Path:
    base = os.environ.get("COS_WORKTREE_ROOT") or str(Path.home() / ".coding-os" / "worktrees")
    return Path(base) / _repo_slug(repo_root)


def _integration_branch() -> str:
    return os.environ.get("COS_GIT_INTEGRATION_BRANCH", "main")


def _agent_session() -> str:
    try:
        from cli.board_commands import _agent_session_id

        sid = _agent_session_id()
    except Exception:  # board_os optional — never break `cos pr` on its absence
        sid = None
    sid = sid or os.environ.get("COS_AGENT_SESSION_ID") or os.environ.get("COS_PANEL_ID")
    return _sanitize(sid) if sid else "nosession"


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
    """True only when the integration branch has a required status check — the
    precondition for arming auto-merge safely. Best-effort; False on any doubt."""
    if not _gh_ready():
        return False
    slug = _git_out(["config", "--get", "remote.origin.url"], cwd=repo)
    if not slug:
        return False
    proc = _run(
        ["gh", "api", f"repos/{{owner}}/{{repo}}/branches/{integration}/protection/required_status_checks"]
    )
    return proc.returncode == 0


def _preflight(repo: str, integration: str) -> dict:
    remote = _has_remote(repo)
    gh = _gh_ready()
    required = _has_required_check(repo, integration) if (remote and gh) else False
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
        "missing": missing,
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
    integration = integration or _integration_branch()
    cap = _preflight(repo, integration)
    _emit({**cap, "mode": "pr" if cap["pr_ok"] else "degraded-trunk"}, as_json)
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
    integration = integration or _integration_branch()
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
    integration = integration or _integration_branch()
    session = _agent_session()
    task_slug = "adhoc" if adhoc else _sanitize(task_id) if task_id else None
    if task_slug is None:
        raise click.ClickException("cos pr submit needs --task <id> or --adhoc.")
    branch = _branch_for(task_slug, session)
    wt = _worktree_root(repo) / f"{task_slug}-{session}"
    if not (wt / ".git").exists():
        raise click.ClickException(f"no open worktree at {wt} — run 'cos pr open' first.")

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

    # Rebase onto the PINNED fetched ref (FETCH_HEAD), never the shared moving
    # branch — branch-guard permits this because the op is worktree-scoped (§5).
    _git(["fetch", "origin", integration], cwd=wt)
    rebase = _git(["rebase", "FETCH_HEAD"], cwd=wt)
    if rebase.returncode != 0:
        _git(["rebase", "--abort"], cwd=wt)
        raise click.ClickException(
            f"rebase onto origin/{integration} conflicted — resolve in the worktree, then retry."
        )

    # sha-pinned lease: pin to the branch's CURRENT remote sha so we never
    # clobber a concurrent push; empty lease for a first push.
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
    armed = False
    if pr_ok and cap["required_check"]:
        # Auto-merge ONLY when a required check exists, else the PR merges with
        # no CI gate. Stays armed; merges itself once the check is green.
        armed = _run(["gh", "pr", "merge", "--auto", "--squash"], cwd=wt).returncode == 0

    _emit(
        {
            "branch": branch,
            "pushed": True,
            "pr_created": pr_ok,
            "pr_url": pr.stdout.strip() if pr_ok else "",
            "auto_merge_armed": armed,
            "required_check": cap["required_check"],
        },
        as_json,
    )


@pr_group.command("status", help="List this repo's pr-mode worktrees, branches, and open PRs.")
@click.option("--repo", "repo_opt", default=None)
@click.option("--json", "as_json", is_flag=True)
def pr_status(repo_opt: str | None, as_json: bool) -> None:
    repo = _resolve_repo(repo_opt)
    wt_root = _worktree_root(repo)
    worktrees = []
    if wt_root.is_dir():
        worktrees = sorted(p.name for p in wt_root.iterdir() if p.is_dir())
    branches = [
        b.strip().lstrip("* ").strip()
        for b in _git_out(["branch", "--list", "agents/*"], cwd=repo).splitlines()
        if b.strip()
    ]
    prs = ""
    if _gh_ready():
        prs = _run(
            ["gh", "pr", "list", "--search", "head:agents/", "--json", "number,headRefName,state"],
            cwd=repo,
        ).stdout.strip()
    _emit(
        {
            "worktree_root": str(wt_root),
            "worktrees": ",".join(worktrees) or "(none)",
            "agent_branches": ",".join(branches) or "(none)",
            "open_prs": prs or "(gh unavailable)",
        },
        as_json,
    )


@pr_group.command("cleanup", help="Remove the worktree + delete the branch + prune (post-merge).")
@click.option("--task", "task_id", default=None)
@click.option("--adhoc", is_flag=True)
@click.option("--repo", "repo_opt", default=None)
@click.option("--json", "as_json", is_flag=True)
def pr_cleanup(task_id: str | None, adhoc: bool, repo_opt: str | None, as_json: bool) -> None:
    repo = _resolve_repo(repo_opt)
    session = _agent_session()
    task_slug = "adhoc" if adhoc else _sanitize(task_id) if task_id else None
    if task_slug is None:
        raise click.ClickException("cos pr cleanup needs --task <id> or --adhoc.")
    branch = _branch_for(task_slug, session)
    wt = _worktree_root(repo) / f"{task_slug}-{session}"

    removed_wt = _git(["worktree", "remove", "--force", str(wt)], cwd=repo).returncode == 0
    deleted_branch = _git(["branch", "-D", branch], cwd=repo).returncode == 0
    _git(["worktree", "prune"], cwd=repo)
    _emit(
        {"worktree_removed": removed_wt, "branch_deleted": deleted_branch, "worktree": str(wt)},
        as_json,
    )
