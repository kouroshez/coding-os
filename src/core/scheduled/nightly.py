#!/usr/bin/env python3
"""
Coding OS — Nightly maintenance script (CRON A).

Runs per-project: decay · learn_extract · routing_recalc.
Each task is independently gated and recorded in last_run.json.

See docs/engineering/scheduled-jobs.md for full contract.
"""

from __future__ import annotations

import argparse
import json
import logging
import logging.handlers
import os
import sqlite3
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrap: make thinking_os importable (same as other standalone scripts)
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve().parent
_THINKING_OS = _HERE.parent / "thinking_os"
if str(_THINKING_OS) not in sys.path:
    sys.path.insert(0, str(_THINKING_OS))

from scheduled._activity import (  # noqa: E402
    outcomes_since_marker,
)
from scheduled._state import (  # noqa: E402
    now_iso,
    read_registry,
    read_state,
    state_dir,
    touch_marker,
    write_state,
)
from scheduled.config import load_config  # noqa: E402

# ---------------------------------------------------------------------------
# Logging — global rotating log + stderr for foreground runs
# ---------------------------------------------------------------------------

_LOG_DIR = Path.home() / ".coding-os" / "scheduled"
_LOG_FILE = _LOG_DIR / "nightly.log"
_DECAY_THROTTLE_DAYS = 7
_MIN_OUTCOMES = 3
_CRON_B_OBS_THRESHOLD = 10
_MAX_CONSECUTIVE_FAILURES = 3
_SCHEMA_VERSION_MIN = 7
_GRAPH_REINDEX_THRESHOLD_S = 86400  # 24h — match doctor_graph.FRESHNESS_SECONDS


def _setup_logging(verbose: bool = False) -> None:
    from core.logging_os import setup as _logging_os_setup

    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    _logging_os_setup(level="debug" if verbose else "info")

    fmt = logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    fh = logging.handlers.RotatingFileHandler(_LOG_FILE, maxBytes=100_000, backupCount=10)
    fh.setFormatter(fmt)
    logging.getLogger().addHandler(fh)


logger = logging.getLogger("codingos.scheduled.nightly")


# ---------------------------------------------------------------------------
# Schema guard
# ---------------------------------------------------------------------------


def _schema_ok(db_path: Path) -> bool:
    try:
        with sqlite3.connect(str(db_path), timeout=5) as conn:
            row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
            if row and row[0] is not None:
                return int(row[0]) >= _SCHEMA_VERSION_MIN
            return False
    except sqlite3.Error as exc:
        logger.debug("schema check failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Task: decay
# ---------------------------------------------------------------------------


def _run_decay(
    db_path: Path,
    project_root: Path,
    *,
    dry_run: bool,
    throttle_days: int = _DECAY_THROTTLE_DAYS,
    prune_days: int = 90,
) -> dict:
    """Run confidence decay via decay.run_decay_locked — the shared throttle+flock
    entry point so nightly never double-decays or races session_enrich."""
    marker = project_root / ".coding-os" / ".last-decay"
    try:
        from decay import run_decay_locked

        return run_decay_locked(
            db_path,
            throttle_days=throttle_days,
            archive_prune_days=prune_days,
            dry_run=dry_run,
            marker_path=marker,
        )
    except ImportError as exc:
        logger.warning("decay task import error (decay.py missing?): %s", exc)
        return {"status": "error", "error": str(exc)}
    except Exception as exc:
        logger.warning("decay task unexpected error: %s", exc)
        return {"status": "error", "error": str(exc)}


# ---------------------------------------------------------------------------
# Task: learn_extract
# ---------------------------------------------------------------------------


def _run_learn_extract(
    db_path: Path,
    project_root: Path,
    *,
    dry_run: bool,
    min_outcomes: int = _MIN_OUTCOMES,
) -> dict:
    """Mine patterns from task_outcomes; gated on new outcomes since last run."""
    marker = state_dir(project_root) / ".last-extract"

    new_outcomes = outcomes_since_marker(db_path, marker)
    if new_outcomes == 0:
        return {"status": "skipped", "reason": "no_new_outcomes"}

    try:
        with sqlite3.connect(str(db_path), timeout=10) as conn:
            conn.row_factory = sqlite3.Row
            total = conn.execute("SELECT COUNT(*) FROM task_outcomes").fetchone()[0]
            if total < min_outcomes:
                return {
                    "status": "skipped",
                    "reason": f"insufficient_data (need {min_outcomes}, have {total})",
                }

    except sqlite3.Error as exc:
        return {"status": "error", "error": str(exc)}

    if dry_run:
        return {"status": "dry_run", "would_run": True, "new_outcomes": new_outcomes}

    try:
        from tools.learning import learn_extract

        with sqlite3.connect(str(db_path), timeout=10) as conn:
            conn.row_factory = sqlite3.Row
            result = learn_extract(conn)

        touch_marker(marker)
        return {"status": "ok", **result}

    except ImportError as exc:
        logger.warning("learn_extract import error: %s", exc)
        return {"status": "error", "error": str(exc)}
    except sqlite3.Error as exc:
        logger.warning("learn_extract db error: %s", exc)
        return {"status": "error", "error": str(exc)}
    except Exception as exc:
        logger.warning("learn_extract unexpected error: %s", exc)
        return {"status": "error", "error": str(exc)}


# ---------------------------------------------------------------------------
# Task: routing_recalc
# ---------------------------------------------------------------------------


def _run_routing_recalc(db_path: Path, *, dry_run: bool) -> dict:
    """Recalculate routing weights if drift detected."""
    try:
        from tools.routing import recalculate_weights, routing_drift

        with sqlite3.connect(str(db_path), timeout=10) as conn:
            conn.row_factory = sqlite3.Row
            drift = routing_drift(conn)

        if not drift.get("drift_detected", False):
            return {
                "status": "skipped",
                "reason": drift.get("reason", "no_drift"),
            }

        if dry_run:
            return {
                "status": "dry_run",
                "would_run": True,
                "drift": drift,
            }

        with sqlite3.connect(str(db_path), timeout=10) as conn:
            conn.row_factory = sqlite3.Row
            result = recalculate_weights(conn)
        return {"status": "ok", **result}

    except ImportError as exc:
        logger.warning("routing_recalc import error: %s", exc)
        return {"status": "error", "error": str(exc)}
    except sqlite3.Error as exc:
        logger.warning("routing_recalc db error: %s", exc)
        return {"status": "error", "error": str(exc)}
    except Exception as exc:
        logger.warning("routing_recalc unexpected error: %s", exc)
        return {"status": "error", "error": str(exc)}


# ---------------------------------------------------------------------------
# CRON B info block (not executed here — printed for make cron-b-setup)
# ---------------------------------------------------------------------------

CRON_B_PROMPT = """\
You are a coding-os maintenance agent running on a weekly schedule.
For each project in ~/.coding-os/registry.json:
  1. Read .coding-os/scheduled/last_run.json to get last_narrative_at.
  2. Count observations added since that timestamp via cos_search or direct DB read.
  3. If count >= 10: call cos_learn_narrative to synthesize insights.
     Write last_narrative_at = <now> to last_run.json.
  4. If count < 10: skip this project.
Use only cos_* MCP tools for DB access. No destructive operations.
Log results to stderr.
"""


# ---------------------------------------------------------------------------
# Per-project run
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Task: digest regenerate
# ---------------------------------------------------------------------------


def _run_digest(db_path: Path, project_root: Path, *, dry_run: bool) -> dict:
    """Regenerate the always-in-context agent digest so a cron-maintained brain
    stays fresh without an interactive SessionStart (digest was startup-only)."""
    if dry_run:
        return {"status": "dry_run", "would_run": True}
    try:
        from digest import regenerate as digest_regenerate

        with sqlite3.connect(str(db_path), timeout=10) as conn:
            conn.row_factory = sqlite3.Row
            result = digest_regenerate(conn, project_root=project_root)
        return {"status": result.get("status", "ok"), "size_chars": result.get("size_chars")}
    except ImportError as exc:
        logger.warning("digest import error: %s", exc)
        return {"status": "error", "error": str(exc)}
    except sqlite3.Error as exc:
        logger.warning("digest db error: %s", exc)
        return {"status": "error", "error": str(exc)}
    except Exception as exc:  # fail-open
        logger.warning("digest unexpected error: %s", exc)
        return {"status": "error", "error": str(exc)}


def _run_error_sweep(
    db_path: Path, *, dry_run: bool, occ_threshold: int, session_threshold: int
) -> dict:
    """error_sweep — roll up durable errors into log_fingerprints + file board bug tasks (E12)."""
    with sqlite3.connect(str(db_path), timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        if (
            conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='log_fingerprints'"
            ).fetchone()
            is None
        ):
            return {"status": "skipped", "reason": "log_fingerprints not present (pre-v32)"}

        from scheduled.error_sweep import run_error_sweep

        def _create(row: sqlite3.Row, severity: str) -> str | None:
            from board_os.mcp_tools import cos_task_create

            sample = (row["sample_msg"] or "")[:60].replace('"', "'")
            outcome = (
                f"Recurring {row['max_lvl']} from {row['scope']} "
                f"(count={row['count']}, sessions={row['distinct_sessions']}, exc={row['exc_type']}). "
                f"First {row['first_seen']}, last {row['last_seen']}. "
                f"Investigate: cos errors --scope {row['scope']}"
            )
            envelope = cos_task_create(
                conn,
                title=f"[error] {row['scope']}: {sample}",
                swimlane="infra",
                kind="bug",
                priority="P1" if severity == "fatal" else "P2",
                status="icebox",
                ready=True,
                labels=[f"fp:{row['fingerprint']}", "auto-error", "error-sweep"],
                outcome=outcome,
            )
            parsed = json.loads(envelope)
            return parsed.get("data", {}).get("task_id") if parsed.get("ok") else None

        result = run_error_sweep(
            conn,
            create_bug_task=_create,
            occ_threshold=occ_threshold,
            session_threshold=session_threshold,
            dry_run=dry_run,
        )
    return {"status": "ok", **result}


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


def _commit_board_drift_tasks_only(project_root: Path, drifted: int) -> dict:
    import subprocess

    def _git(*args: str, timeout: int) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", "-C", str(project_root), *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    try:
        add = _git("add", "--", "docs/tasks", timeout=30)
        if add.returncode != 0:
            return {"committed": False, "error": f"git add rc={add.returncode}: {add.stderr[-200:]}"}
        msg = f"chore(board): commit {drifted} drifted task file(s) to match the board DB"
        commit = _git("commit", "-m", msg, "--", "docs/tasks", timeout=120)
        if commit.returncode != 0:
            return {"committed": False, "error": f"git commit rc={commit.returncode}: {commit.stderr[-200:]}"}
        sha = _git("rev-parse", "--short", "HEAD", timeout=10).stdout.strip()
        return {"committed": True, "sha": sha, "count": drifted}
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

        drift = detect_board_git_drift(project_root, task_rows_from_db(conn))
        if not drift.is_git_root or drift.skip_reason:
            return {"status": "skipped", "reason": drift.skip_reason or "not a git work-tree root"}
        if not drift.has_drift:
            return {"status": "ok", "drift": False}

        committable = len(drift.untracked) + len(drift.modified)
        autonomy_allows_commit = _git_autonomy(project_root) in _AUTO_COMMIT_AUTONOMY
        if committable and not drift.missing and not dry_run and autonomy_allows_commit:
            result = _commit_board_drift_tasks_only(project_root, committable)
            if result.get("committed"):
                return {
                    "status": "ok",
                    "drift": True,
                    "committed": True,
                    "sha": result.get("sha"),
                    "count": committable,
                }
            logger.warning("[board_coherence] auto-commit failed: %s", result.get("error"))

        existing = conn.execute(
            "SELECT task_id FROM tasks WHERE status NOT IN ('complete', 'archive') "
            "AND labels_json LIKE '%\"auto-git-drift\"%'"
        ).fetchone()
        if existing is not None:
            return {"status": "ok", "drift": True, "filed": False, "existing_task": existing[0]}
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
    return {"status": "ok", "drift": True, "filed": filed, "task_id": task_id}


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


def run_project(project: dict, *, dry_run: bool) -> dict:
    """Run all maintenance tasks for one project."""
    slug = project.get("slug", "?")
    path_str = project.get("path", "")
    project_root = Path(path_str)
    db_path = project_root / ".coding-os" / "coding-os.db"

    run: dict = {
        "slug": slug,
        "path": path_str,
        "run_at": now_iso(),
        "tasks": {},
        "consecutive_failures": 0,
        "last_error": None,
    }

    logger.info("[%s] start (db=%s)", slug, db_path)

    if not db_path.exists():
        run["tasks"]["all"] = {"status": "skipped", "reason": "db_not_found"}
        logger.info("[%s] db not found — skip all", slug)
        return run

    if not _schema_ok(db_path):
        run["tasks"]["all"] = {
            "status": "skipped",
            "reason": f"schema_version < {_SCHEMA_VERSION_MIN}",
        }
        logger.warning("[%s] schema too old — skip all", slug)
        return run

    cfg = load_config(project_root)
    if not cfg["enabled"]:
        run["tasks"]["all"] = {"status": "skipped", "reason": "disabled in scheduled config"}
        logger.info("[%s] scheduled maintenance disabled in config — skip all", slug)
        return run

    prev_state = read_state(project_root)
    consecutive_failures = prev_state.get("consecutive_failures", 0)

    if consecutive_failures >= _MAX_CONSECUTIVE_FAILURES:
        run["consecutive_failures"] = consecutive_failures
        run["last_error"] = prev_state.get("last_error")
        run["tasks"]["all"] = {
            "status": "skipped",
            "reason": f"disabled after {consecutive_failures} consecutive failures",
        }
        logger.warning("[%s] disabled (consecutive_failures=%d)", slug, consecutive_failures)
        return run

    errors = 0

    # Task 1: decay
    try:
        t = _run_decay(
            db_path,
            project_root,
            dry_run=dry_run,
            throttle_days=int(cfg["decay_throttle_days"]),
            prune_days=int(cfg["archive_prune_days"]),
        )
        run["tasks"]["decay"] = t
        logger.info("[%s] decay → %s", slug, t.get("status"))
        if t.get("status") == "error":
            errors += 1
    except Exception as exc:
        run["tasks"]["decay"] = {"status": "error", "error": str(exc)}
        logger.error("[%s] decay raised: %s", slug, exc)
        errors += 1

    # Task 2: learn_extract
    try:
        t = _run_learn_extract(
            db_path,
            project_root,
            dry_run=dry_run,
            min_outcomes=int(cfg["learn_extract_min_outcomes"]),
        )
        run["tasks"]["learn_extract"] = t
        logger.info("[%s] learn_extract → %s", slug, t.get("status"))
        if t.get("status") == "error":
            errors += 1
    except Exception as exc:
        run["tasks"]["learn_extract"] = {"status": "error", "error": str(exc)}
        logger.error("[%s] learn_extract raised: %s", slug, exc)
        errors += 1

    # Task 3: routing_recalc
    try:
        t = _run_routing_recalc(db_path, dry_run=dry_run)
        run["tasks"]["routing_recalc"] = t
        logger.info("[%s] routing_recalc → %s", slug, t.get("status"))
        if t.get("status") == "error":
            errors += 1
    except Exception as exc:
        run["tasks"]["routing_recalc"] = {"status": "error", "error": str(exc)}
        logger.error("[%s] routing_recalc raised: %s", slug, exc)
        errors += 1

    # Task 4: error-sweep — recurring durable errors → board bug tasks (observability eye E12)
    try:
        t = _run_error_sweep(
            db_path,
            dry_run=dry_run,
            occ_threshold=int(cfg.get("error_sweep_occ_threshold", 3)),
            session_threshold=int(cfg.get("error_sweep_session_threshold", 2)),
        )
        run["tasks"]["error_sweep"] = t
        logger.info("[%s] error_sweep → %s", slug, t.get("status"))
        if t.get("status") == "error":
            errors += 1
    except Exception as exc:
        run["tasks"]["error_sweep"] = {"status": "error", "error": str(exc)}
        logger.error("[%s] error_sweep raised: %s", slug, exc)
        errors += 1

    # Task 4.5: reclaim — recover zombie in_progress/testing of dead sessions +
    # auto-archive aged backlog. The unattended-timer: a
    # stagnant board with no new sessions still heals here.
    try:
        t = _run_reclaim(db_path, project_root, dry_run=dry_run)
        run["tasks"]["reclaim"] = t
        logger.info("[%s] reclaim → %s", slug, t.get("status"))
        if t.get("status") == "error":
            errors += 1
    except Exception as exc:
        run["tasks"]["reclaim"] = {"status": "error", "error": str(exc)}
        logger.error("[%s] reclaim raised: %s", slug, exc)
        errors += 1

    # Task 4.65: board_coherence — file an idempotent board task on board↔git
    # drift so no-hook personas (P4/P5/P7) see it without invoking cos doctor.
    try:
        t = _run_board_coherence(db_path, project_root, dry_run=dry_run)
        run["tasks"]["board_coherence"] = t
        logger.info("[%s] board_coherence → %s", slug, t.get("status"))
        if t.get("status") == "error":
            errors += 1
    except Exception as exc:
        run["tasks"]["board_coherence"] = {"status": "error", "error": str(exc)}
        logger.error("[%s] board_coherence raised: %s", slug, exc)
        errors += 1

    # Task 4.6: dep_reconcile — re-block reopened deps + surface unblocked-but-
    # unauthored and long-blocked tasks across the whole graph (TASK-415).
    try:
        t = _run_dep_reconcile(db_path, project_root, dry_run=dry_run)
        run["tasks"]["dep_reconcile"] = t
        logger.info("[%s] dep_reconcile → %s", slug, t.get("status"))
        if t.get("status") == "error":
            errors += 1
    except Exception as exc:
        run["tasks"]["dep_reconcile"] = {"status": "error", "error": str(exc)}
        logger.error("[%s] dep_reconcile raised: %s", slug, exc)
        errors += 1

    # Task 3.5: digest regenerate (after extract/decay so it reflects new patterns)
    try:
        t = _run_digest(db_path, project_root, dry_run=dry_run)
        run["tasks"]["digest"] = t
        logger.info("[%s] digest → %s", slug, t.get("status"))
        if t.get("status") == "error":
            errors += 1
    except Exception as exc:
        run["tasks"]["digest"] = {"status": "error", "error": str(exc)}
        logger.error("[%s] digest raised: %s", slug, exc)
        errors += 1

    # Task 4: graph_reindex_if_stale
    try:
        t = _run_graph_reindex_if_stale(project_root, dry_run=dry_run)
        run["tasks"]["graph_reindex"] = t
        logger.info("[%s] graph_reindex → %s", slug, t.get("status"))
        if t.get("status") == "error":
            errors += 1
    except Exception as exc:
        run["tasks"]["graph_reindex"] = {"status": "error", "error": str(exc)}
        logger.error("[%s] graph_reindex raised: %s", slug, exc)
        errors += 1

    # Failure tracking
    if errors > 0:
        consecutive_failures += 1
        run["last_error"] = f"{errors} task(s) failed at {now_iso()}"
    else:
        consecutive_failures = 0
        run["last_error"] = None

    run["consecutive_failures"] = consecutive_failures

    if consecutive_failures >= _MAX_CONSECUTIVE_FAILURES:
        run["disabled_reason"] = (
            f"auto-disabled: {consecutive_failures} consecutive failures. "
            "Run `make cron-run` to reset and retry."
        )
        logger.error("[%s] auto-disabled after %d failures", slug, consecutive_failures)

    write_state(project_root, run)
    logger.info("[%s] done (errors=%d)", slug, errors)
    return run


# ---------------------------------------------------------------------------
# Task: graph_reindex_if_stale
# ---------------------------------------------------------------------------


def _run_graph_reindex_if_stale(project_root: Path, *, dry_run: bool) -> dict:
    """Trigger a full graph reindex when the backend probe is older than 24h.

    The PostToolUse auto-reindex hook keeps the graph fresh on every Edit /
    Write, but a project that hasn't been touched for >24h drifts out of
    freshness silently. Nightly fills that gap so `cos doctor` keeps
    `graph.freshness` PASS without manual intervention.
    """
    import time as _t

    probe = project_root / ".coding-os" / ".graph-backend.json"
    if not probe.exists():
        return {"status": "skipped", "reason": "no_probe_yet"}
    try:
        data = json.loads(probe.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": "skipped", "reason": f"probe_unreadable: {exc}"}

    last_ok = data.get("last_ok_at")
    if not isinstance(last_ok, int):
        return {"status": "skipped", "reason": "probe_missing_last_ok_at"}
    age = int(_t.time()) - last_ok
    if age < _GRAPH_REINDEX_THRESHOLD_S:
        return {
            "status": "skipped",
            "reason": f"fresh ({age}s < {_GRAPH_REINDEX_THRESHOLD_S}s)",
            "age_seconds": age,
        }

    if dry_run:
        return {"status": "dry_run", "would_reindex": True, "age_seconds": age}

    import subprocess

    # Invoke via `sys.executable -m cli.main graph-reindex` so launchd's
    # stripped PATH (typically /usr/bin:/bin) cannot lose the binary —
    # the interpreter we are already running with always resolves.
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "cli.main", "graph-reindex"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=600,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return {"status": "error", "error": str(exc)}

    if completed.returncode != 0:
        return {
            "status": "error",
            "error": f"cos graph-reindex rc={completed.returncode}",
            "stderr_tail": completed.stderr[-500:],
        }
    summary_line = ""
    for line in reversed(completed.stdout.splitlines()):
        if "processed=" in line:
            summary_line = line.strip()
            break
    return {"status": "ok", "summary": summary_line or "completed", "age_seconds": age}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="coding-os nightly maintenance")
    parser.add_argument("--dry-run", action="store_true", help="simulate without writing")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument(
        "--project",
        metavar="SLUG",
        help="run only this project slug",
    )
    parser.add_argument(
        "--reset-failures",
        action="store_true",
        help="clear consecutive_failures counter for all projects before running",
    )
    args = parser.parse_args(argv)

    _setup_logging(args.verbose)
    logger.info("=== nightly start dry_run=%s ===", args.dry_run)

    projects = read_registry()
    if args.project:
        projects = [p for p in projects if p.get("slug") == args.project]
        if not projects:
            logger.error("project slug %r not found in registry", args.project)
            return 1

    if args.reset_failures:
        for proj in projects:
            root = Path(proj.get("path", ""))
            state = read_state(root)
            if state.get("consecutive_failures", 0) > 0:
                state["consecutive_failures"] = 0
                state["last_error"] = None
                state.pop("disabled_reason", None)
                write_state(root, state)
                logger.info("[%s] consecutive_failures reset", proj.get("slug"))

    results = []
    for proj in projects:
        try:
            r = run_project(proj, dry_run=args.dry_run)
            results.append(r)
        except Exception as exc:
            slug = proj.get("slug", "?")
            logger.error("[%s] unhandled error: %s", slug, exc)
            results.append({"slug": slug, "error": str(exc)})

    summary = {
        "run_at": now_iso(),
        "dry_run": args.dry_run,
        "projects_processed": len(results),
        "projects": results,
    }

    global_log = _LOG_DIR / "last_summary.json"
    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        global_log.write_text(json.dumps(summary, indent=2, default=str))
    except OSError as exc:
        logger.warning("could not write global summary: %s", exc)

    logger.info("=== nightly done projects=%d ===", len(results))

    errors_total = sum(1 for r in results if r.get("last_error") or r.get("error"))
    return 1 if errors_total > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
