"""Nightly board-maintenance legs — coherence, reclaim, dependency reconcile.

Board drift is detected against git, and only committed when the project's
declared autonomy allows it — an unattended run must never surprise the
operator with a commit they did not authorise.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from pathlib import Path

logger = logging.getLogger("codingos.scheduled.nightly")

_AUTO_COMMIT_AUTONOMY = ("local", "local_autonomous", "autonomous")


def _git_autonomy(project_root: Path) -> str:
    env = os.environ.get("COS_GIT_AUTONOMY")
    if env and env.strip():
        return env.strip()
    try:
        raw = json.loads((project_root / ".coding-os" / "hub-settings.json").read_text())
        level = (raw.get("git_settings") or {}).get("autonomy_level")
        if isinstance(level, str) and level.strip():
            return level.strip()
    except (OSError, ValueError, AttributeError) as exc:
        logger.debug("git autonomy read failed: %s", exc)
    return "draft"


def _commit_board_drift_tasks_only(project_root: Path, paths: list[str]) -> dict:
    import subprocess

    def _git(*args: str, timeout: int) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", "-C", str(project_root), *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    try:
        add = _git("add", "--", *paths, timeout=30)
        if add.returncode != 0:
            return {
                "committed": False,
                "error": f"git add rc={add.returncode}: {add.stderr[-200:]}",
            }
        msg = f"chore(board): commit {len(paths)} drifted task file(s) to match the board DB"
        # The repo pre-commit hook scales with staged-file count; 368 files
        # measured >120s. A premature timeout mis-reports a landed commit as
        # failed and files a spurious drift task.
        commit = _git("commit", "-m", msg, "--", *paths, timeout=600)
        if commit.returncode != 0:
            return {
                "committed": False,
                "error": f"git commit rc={commit.returncode}: {commit.stderr[-200:]}",
            }
        sha = _git("rev-parse", "--short", "HEAD", timeout=10).stdout.strip()
        return {"committed": True, "sha": sha, "count": len(paths)}
    except (OSError, subprocess.SubprocessError) as exc:
        return {"committed": False, "error": str(exc)}


def _run_board_coherence(db_path: Path, project_root: Path, *, dry_run: bool) -> dict:
    """board_coherence — auto-commit board↔git drift (autonomy-gated) or file an idempotent task."""
    from board_os.git_coherence import detect_board_git_drift, task_rows_from_db

    with sqlite3.connect(str(db_path), timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        if (
            conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='tasks'"
            ).fetchone()
            is None
        ):
            return {"status": "skipped", "reason": "no tasks table"}

        rows = task_rows_from_db(conn)
        drift = detect_board_git_drift(project_root, rows)
        if not drift.is_git_root or drift.skip_reason:
            return {"status": "skipped", "reason": drift.skip_reason or "not a git work-tree root"}
        if not drift.has_drift:
            return {"status": "ok", "drift": False}

        # Missing rows (DB row, no file) cannot be fixed by a commit and must
        # not block it — one orphaned row would pin every other drifted file
        # dirty forever. Commit the committable set; missing still files below.
        path_by_id = dict(rows)
        committable_paths = sorted(
            {
                path_by_id[task_id]
                for task_id in (*drift.untracked, *drift.modified)
                if path_by_id.get(task_id)
            }
        )
        autonomy_allows_commit = _git_autonomy(project_root) in _AUTO_COMMIT_AUTONOMY
        committed_sha: str | None = None
        if committable_paths and not dry_run and autonomy_allows_commit:
            result = _commit_board_drift_tasks_only(project_root, committable_paths)
            if result.get("committed"):
                committed_sha = result.get("sha")
                if not drift.missing:
                    return {
                        "status": "ok",
                        "drift": True,
                        "committed": True,
                        "sha": committed_sha,
                        "count": len(committable_paths),
                    }
            else:
                logger.warning("[board_coherence] auto-commit failed: %s", result.get("error"))

        partial = {"committed": True, "sha": committed_sha} if committed_sha else {}
        existing = conn.execute(
            "SELECT task_id FROM tasks WHERE status NOT IN ('complete', 'archive') "
            "AND labels_json LIKE '%\"auto-git-drift\"%'"
        ).fetchone()
        if existing is not None:
            return {
                "status": "ok",
                "drift": True,
                "filed": False,
                "existing_task": existing[0],
                **partial,
            }
        if dry_run:
            return {"status": "ok", "drift": True, "filed": False, "dry_run": True}

        from board_os.mcp_tools import cos_task_create

        envelope = cos_task_create(
            conn,
            title=(
                f"[board-drift] {len(drift.untracked)} untracked / "
                f"{len(drift.modified)} modified / {len(drift.missing)} missing task file(s)"
            ),
            swimlane="infra",
            kind="chore",
            priority="P2",
            status="icebox",
            ready=True,
            labels=["auto-git-drift", "board-coherence"],
            outcome=(
                drift.summary()
                + " — commit the untracked/modified docs/tasks/*.md (or reconcile the DB rows) "
                "so the board (DB) and git agree."
            ),
            acceptance=(
                "**Given** board↔git drift (untracked/modified/missing docs/tasks/*.md) "
                "**When** the drifted files are committed (or the orphaned DB rows reconciled) "
                "**Then** `cos doctor` board.git_tracked reports no drift."
            ),
            read_first=["docs/governance/task-lifecycle.md", "src/core/board_os/git_coherence.py"],
        )
        parsed = json.loads(envelope)
        task_id = parsed.get("data", {}).get("task_id") if parsed.get("ok") else None
        filed = task_id is not None
        if not filed:
            logger.warning("[board_coherence] drift-task filing failed: %s", envelope[:200])
    return {"status": "ok", "drift": True, "filed": filed, "task_id": task_id, **partial}


def _run_reclaim(db_path: Path, project_root: Path, *, dry_run: bool) -> dict:
    """reclaim — recover zombie in_progress/testing tasks of dead sessions and
    auto-archive aged backlog (TASK-210 RC4). This is the UNATTENDED-TIMER leg:
    an idle board with no new sessions (so the SessionStart sweep never fires)
    still heals here. cos_task_reclaim resolves project context from
    COS_PROJECT_ROOT, so we scope it to this project for the call."""
    from board_os.config import load_config as _load_board_cfg
    from board_os.mcp_tools import _archive_stale_sweep, cos_task_reclaim

    prev_root = os.environ.get("COS_PROJECT_ROOT")
    os.environ["COS_PROJECT_ROOT"] = str(project_root)
    try:
        with sqlite3.connect(str(db_path), timeout=10) as conn:
            if (
                conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='tasks'"
                ).fetchone()
                is None
            ):
                return {"status": "skipped", "reason": "tasks table not present"}
            env = json.loads(cos_task_reclaim(conn, dry_run=dry_run))
            reclaimed = env.get("data", {}).get("reclaimed", []) if env.get("ok") else []
            archived: list = []
            if not dry_run:
                try:
                    archived = _archive_stale_sweep(conn, _load_board_cfg(project_root))
                except Exception as exc:
                    logger.debug("[reclaim] archive sweep skipped: %s", exc)
        return {
            "status": "ok",
            "reclaimed": len(reclaimed),
            "auto_archived": len(archived),
            "dry_run": dry_run,
        }
    finally:
        if prev_root is None:
            os.environ.pop("COS_PROJECT_ROOT", None)
        else:
            os.environ["COS_PROJECT_ROOT"] = prev_root


def _run_dep_reconcile(db_path: Path, project_root: Path, *, dry_run: bool) -> dict:
    """dep_reconcile — re-block tasks whose dependency reopened + surface
    unblocked-but-unauthored and long-blocked tasks across the whole graph
    (the gaps the per-completion cascade cannot reach, TASK-415). Reuses
    board_os.cascade_ready_dependents; cos_task_move resolves file paths from
    COS_PROJECT_ROOT, so scope it to this project for the call."""
    from scheduled.dep_reconcile import run_dep_reconcile

    prev_root = os.environ.get("COS_PROJECT_ROOT")
    os.environ["COS_PROJECT_ROOT"] = str(project_root)
    try:
        with sqlite3.connect(str(db_path), timeout=10) as conn:
            conn.row_factory = sqlite3.Row
            return run_dep_reconcile(conn, dry_run=dry_run)
    finally:
        if prev_root is None:
            os.environ.pop("COS_PROJECT_ROOT", None)
        else:
            os.environ["COS_PROJECT_ROOT"] = prev_root
