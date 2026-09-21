"""Reclaiming abandoned work in bulk: reap and heal.

Private module of pr_commands.py — import through that facade.
"""

from __future__ import annotations

import json
import os
import re
import socket
import sys
import time
from pathlib import Path

try:
    import fcntl
except ImportError:  # non-POSIX (Windows) — the reaper lock degrades to a no-op
    fcntl = None  # type: ignore[assignment]

import click

from cli._pr_shared import (
    _agent_session,
    _branch_for,
    _branch_recoverable,
    _emit,
    _env_int,
    _escalate_blocked,
    _gh_ready,
    _git,
    _git_out,
    _has_remote,
    _heal_budget,
    _heal_budget_clear,
    _heal_budget_save,
    _heal_lock,
    _integration_branch,
    _preserve_reaped,
    _resolve_repo,
    _run,
    _sanitize,
    _session_state,
    _unqualify_head,
    _worktree_root,
    pr_group,
)


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


def _worktree_lock_reason(repo: str, wt: Path) -> str:
    # `git worktree list --porcelain` emits `locked <reason>` verbatim for a locked
    # worktree; return the reason of the block whose path resolves to wt.
    out = _git_out(["worktree", "list", "--porcelain"], cwd=repo)
    target = wt.resolve()
    current: Path | None = None
    for line in out.splitlines():
        if line.startswith("worktree "):
            try:
                current = Path(line[len("worktree ") :]).resolve()
            except OSError:
                current = None
        elif line.startswith("locked") and current == target:
            return line[len("locked") :].strip()
    return ""


def _worktree_index(repo: str) -> dict[Path, dict]:
    # One `git worktree list --porcelain` dump → {resolved path: {"branch","locked"}}.
    # The reaper sweep reads branch + lock reason from this instead of re-forking the
    # full list (and a rev-parse) per candidate — O(N) per sweep, not O(K·N), on a
    # path pr-reap.sh backgrounds at every SessionStart.
    index: dict[Path, dict] = {}
    cur: Path | None = None
    for line in _git_out(["worktree", "list", "--porcelain"], cwd=repo).splitlines():
        if line.startswith("worktree "):
            try:
                cur = Path(line[len("worktree ") :].strip()).resolve()
            except OSError:
                cur = None
            if cur is not None:
                index[cur] = {"branch": "", "locked": ""}
        elif cur is not None and cur in index:
            if line.startswith("branch "):
                index[cur]["branch"] = _unqualify_head(line[len("branch ") :].strip())
            elif line.startswith("locked"):
                index[cur]["locked"] = line[len("locked") :].strip()
    return index


def _lock_owner_alive(repo: str, wt: Path, reason: str | None = None) -> bool:
    # True when the lock reason names an owner=<pid> alive on THIS host — the owner
    # agent is still up despite a missing presence record, so an unknown + age-stale
    # worktree must NOT be reaped. Pass `reason` from a hoisted _worktree_index to skip
    # the per-candidate porcelain fork. Owner liveness is host-local: a pid only proves
    # life on the host that stamped it, so a CLEAN host token (ASCII, no C-quote
    # artifacts) that differs from ours is a FOREIGN owner → never a keep (a foreign pid
    # could collide with a live local pid). A non-ASCII host gets the whole reason
    # C-quoted by git, so an unclean/empty host falls back to the pid-only check (a live
    # local owner with a mangled host is not wrongly reaped); the reap preserves work first.
    text = reason if reason is not None else _worktree_lock_reason(repo, wt)
    match = re.search(r"owner=(\d+)(?:@(\S+))?", text)
    if not match:
        return False
    pid, host = int(match.group(1)), (match.group(2) or "")
    host_is_clean = bool(host) and '"' not in host and "\\" not in host
    if host_is_clean and host != socket.gethostname():
        return False
    try:
        from core.board_os.presence import pid_alive
    except Exception:
        return False
    return pid_alive(pid)


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
            kept.append(
                {"branch": branch, "remote_pending": remote_pending, "pr_pending": pr_pending}
            )
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
    # are the WORK and must survive. So: preserve whenever the branch is not
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


@pr_group.command(
    "reap", help="GC worktrees/branches/PRs of presence-offline sessions; drain the cleanup ledger."
)
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
                    {
                        "reaped": 0,
                        "kept_live": 0,
                        "ledger_drained": "(skipped: reaper already running)",
                    },
                    as_json,
                )
                return
        wt_root = _worktree_root(repo)
        drained = [] if dry_run else _drain_ledger(repo)
        reaped: list[dict] = []
        kept: list[dict] = []
        wt_index = _worktree_index(repo)  # one porcelain dump for the whole sweep
        if wt_root.is_dir():
            for wt in sorted(p for p in wt_root.iterdir() if p.is_dir()):
                entry = wt_index.get(wt.resolve(), {})
                branch = entry.get("branch") or _git_out(
                    ["rev-parse", "--abbrev-ref", "HEAD"], cwd=wt
                )
                if not branch.startswith("agents/"):
                    continue
                session = branch.rsplit("/", 1)[-1]
                state = _session_state(session, repo)
                reapable = state == "offline" or (
                    state == "unknown"
                    and _worktree_stale(wt)
                    and not _lock_owner_alive(repo, wt, reason=entry.get("locked", ""))
                )
                if reapable:
                    reaped.append(
                        {"worktree": str(wt), "branch": branch, "would_reap": True}
                        if dry_run
                        else _reap_one(repo, wt, branch)
                    )
                else:
                    if not dry_run:
                        # Re-assert the lock so a peer's prune can't drop a live checkout (§2).
                        # A no-op when already locked (the common case), so it preserves the
                        # owner=pid@host stamp the open wrote — that is what a later sweep reads.
                        _git(
                            ["worktree", "lock", str(wt), "--reason", "pr-mode live session"],
                            cwd=repo,
                        )
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


@pr_group.command(
    "heal",
    help="Record a self-heal attempt on a red PR; escalate to blocked when the budget is spent.",
)
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
