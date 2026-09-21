"""Starting work: preflight and open.

Private module of pr_commands.py — import through that facade.
"""

from __future__ import annotations

import json
import os
import socket
import sys
from pathlib import Path

try:
    import fcntl
except ImportError:  # non-POSIX (Windows) — the reaper lock degrades to a no-op
    fcntl = None  # type: ignore[assignment]

import click

from cli._pr_shared import (
    _agent_session,
    _branch_for,
    _emit,
    _git,
    _git_settings,
    _integration_branch,
    _main_repo_root,
    _preflight,
    _resolve_repo,
    _run,
    _sanitize,
    _unprotected_warning,
    _worktree_root,
    pr_group,
)


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


def _worktree_exclude(wt: Path) -> Path | None:
    proc = _run(["git", "rev-parse", "--git-path", "info/exclude"], cwd=str(wt))
    out = proc.stdout.strip()
    if proc.returncode != 0 or not out:
        return None
    path = Path(out)
    return path if path.is_absolute() else (wt / path)


def _exclude_in_worktree(exclude: Path | None, rel: str) -> None:
    # A symlink named after a trailing-slash gitignore pattern (node_modules/) is
    # NOT matched by that pattern and would leak into the PR — so root-anchor the
    # linked path in the worktree's git exclude. Shared common-dir file: dedup, and
    # the entries are already-gitignored names so polluting it is harmless.
    if exclude is None:
        return
    entry = f"/{rel}"
    try:
        existing = exclude.read_text().splitlines() if exclude.exists() else []
        if entry not in existing:
            with exclude.open("a") as handle:
                handle.write(f"{entry}\n")
    except OSError as exc:
        click.echo(f"cos pr: could not update worktree exclude for {rel}: {exc}", err=True)


def _run_setup(wt: Path, cmd: str) -> str:
    # The consumer's one-time worktree setup (e.g. `npm ci`) — generous timeout, a
    # real install legitimately exceeds the 120s gh/git default. Non-fatal: the
    # worktree is usable, the agent just sees the warning at validate time.
    try:
        timeout = max(1, int(os.environ.get("COS_PR_SETUP_TIMEOUT", "600")))
    except ValueError:
        timeout = 600
    proc = _run(["bash", "-lc", cmd], cwd=str(wt), timeout=timeout)
    if proc.returncode != 0:
        click.echo(
            f"cos pr: worktree setup '{cmd}' failed (exit {proc.returncode}) — "
            f"the validate command may fail until deps are installed.",
            err=True,
        )
        return f"failed (exit {proc.returncode})"
    return "ok"


def _bootstrap_worktree(repo: str, wt: Path) -> dict:
    # A fresh worktree is a clean checkout with NO gitignored deps (node_modules,
    # .venv, Pods) and NO local secrets (.env), so the agent's first validate
    # command fails. Opt-in per project (git_settings): symlink the declared
    # gitignored paths in from the main checkout and run a one-time setup command.
    # No config → no-op, byte-identical to no bootstrap.
    settings = _git_settings(repo)
    includes = settings.get("worktree_include")
    setup_cmd = settings.get("worktree_setup_cmd")
    linked: list[str] = []
    if isinstance(includes, list) and includes:
        main_root = Path(_main_repo_root(repo))
        exclude = _worktree_exclude(wt)
        for raw in includes:
            if not isinstance(raw, str) or not raw.strip():
                continue
            rel = raw.strip()
            # Containment — never link a path outside the worktree. Only the project
            # owner writes this config (the agent is blocked from hub-settings.json),
            # so this just guards the owner's own typo, but cheaply.
            if rel.startswith("/") or ".." in Path(rel).parts:
                continue
            src, dst = main_root / rel, wt / rel
            if not src.exists() or os.path.lexists(dst):
                continue
            try:
                dst.parent.mkdir(parents=True, exist_ok=True)
                os.symlink(src, dst)
            except OSError as exc:
                click.echo(f"cos pr: could not link {rel}: {exc}", err=True)
                continue
            linked.append(rel)
            _exclude_in_worktree(exclude, rel)
    setup = (
        _run_setup(wt, setup_cmd.strip())
        if isinstance(setup_cmd, str) and setup_cmd.strip()
        else None
    )
    return {"linked": linked, "setup": setup}


def _bootstrap_summary(bootstrap: dict) -> str:
    parts = []
    if bootstrap.get("linked"):
        parts.append("linked=" + ",".join(bootstrap["linked"]))
    if bootstrap.get("setup"):
        parts.append("setup=" + bootstrap["setup"])
    return " ".join(parts) or "(none)"


@pr_group.command("preflight", help="Check pr-mode capability (remote + gh + required CI).")
@click.option("--repo", "repo_opt", default=None, help="Repo path (default: cwd).")
@click.option(
    "--integration",
    default=None,
    help="Integration branch (default: COS_GIT_INTEGRATION_BRANCH or main).",
)
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
@click.option(
    "--task", "task_id", default=None, help="Board task id (else claim the next ready task)."
)
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
    # session's checkout. On an idempotent re-open the tree is already locked and
    # `git worktree lock` would no-op, stranding a previous (possibly dead) owner
    # pid in the reason — unlock first so the stamp refreshes to THIS session's live
    # pid (a peer reaper keeps a presence-live worktree regardless of the reason).
    if already:
        _git(["worktree", "unlock", str(wt)], cwd=repo)
    _git(["worktree", "lock", str(wt), "--reason", _live_lock_reason(repo, session)], cwd=repo)

    # Bootstrap deps/secrets only on a freshly created checkout.
    bootstrap = _bootstrap_worktree(repo, wt) if not already else {"linked": [], "setup": None}

    _emit(
        {
            "worktree": str(wt),
            "branch": branch,
            "task": task_id or "(adhoc)",
            "integration": integration,
            "project_root": repo,
            "mode": "pr" if cap["pr_ok"] else "degraded-trunk",
            "missing": ",".join(cap["missing"]) or "(none)",
            "bootstrap": _bootstrap_summary(bootstrap),
            "next": f"export COS_PROJECT_ROOT={repo}  # then edit inside {wt}",
        },
        as_json,
    )


def _owner_pid_host(repo: str, session: str) -> tuple[int, str]:
    # The agent runtime pid (the $PPID the presence hook records) + its host, read
    # from THIS session's presence record while it still exists at `cos pr open`.
    # Snapshotting it into the worktree lock reason lets the reaper recognise a
    # live owner even after the presence record is later rotated or deleted.
    state_dir = Path(repo) / ".coding-os"
    for sess_dir in sorted(state_dir.glob("*/sessions")):
        jf = sess_dir / f"{session}.json"
        if not jf.is_file():
            continue
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        pid = int(data.get("pid") or 0)
        if pid > 0:
            return pid, data.get("host") or socket.gethostname()
    return 0, ""


def _live_lock_reason(repo: str, session: str) -> str:
    # Worktree lock reason carrying owner=<pid>@<host> when derivable, so the
    # reaper can skip a live owner whose presence record vanished. Falls back to
    # the bare reason (back-compat) when no presence pid is available.
    pid, host = _owner_pid_host(repo, session)
    base = f"pr-mode session {session}"
    return f"{base} owner={pid}@{host}" if pid > 0 else base
