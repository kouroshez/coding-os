"""Helpers and the click group every `cos pr` subcommand builds on.

Private module of pr_commands.py — import through that facade.
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

_AUTONOMY_LEVELS = ("local", "local_autonomous", "draft", "auto_merge", "autonomous")


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
        [
            "gh",
            "api",
            f"repos/{{owner}}/{{repo}}/branches/{integration}/protection/required_status_checks",
        ],
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
        names.add(name[len("origin/") :] if name.startswith("origin/") else name)
    return sorted(names)


def _git_state(repo: str) -> dict:
    # Real repo state for the Config Git tab — local git only, so it
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


def _branch_for(task_slug: str, session: str) -> str:
    return f"agents/{task_slug}/{session}"


def _resolve_worktree(repo: str, task_slug: str, session: str) -> tuple[Path, str]:
    # Find the worktree+branch `open` created, even when the session id differs
    # across processes (the pid-<getpid> fallback gives a fresh value per process,
    # Fast path: the session-derived path exists. Else scan this repo's
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
        return wt, _git_out(["rev-parse", "--abbrev-ref", "HEAD"], cwd=wt) or _branch_for(
            task_slug, session
        )
    return computed, _branch_for(task_slug, session)


def _resolve_repo(repo_opt: str | None) -> str:
    repo = _toplevel(repo_opt or os.getcwd())
    if repo is None:
        raise click.ClickException(
            "not inside a git repository — cos pr needs a git checkout (run 'git init' first)."
        )
    return repo


@click.group("pr", help="pr-mode multi-agent git executor (worktree → PR → CI → merge → cleanup).")
def pr_group() -> None:
    pass


def _unqualify_head(ref: str) -> str:
    return ref[len("refs/heads/") :] if ref.startswith("refs/heads/") else ref


def _branch_recoverable(repo: str, branch: str, integration: str) -> bool:
    # gh-independent cleanup safety net: True when every branch commit is already
    # reachable from an origin ref (or the local integration), so deleting the
    # local branch loses nothing.
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
    # . Commit any uncommitted/untracked work onto the (doomed) branch —
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
            [
                "-c",
                "user.email=reaper@coding-os",
                "-c",
                "user.name=cos-reaper",
                "commit",
                "-q",
                "--no-verify",
                "-m",
                f"chore: preserve reaped agent work ({branch})",
            ],
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
