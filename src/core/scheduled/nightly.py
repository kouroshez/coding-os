#!/usr/bin/env python3
"""
Coding OS — Nightly maintenance script (CRON A).

Runs per-project: decay · learn_extract · routing_recalc.
Each task is independently gated and recorded in last_run.json.

See docs/engineering/scheduled-jobs.md for full contract.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import logging
import logging.handlers
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

from _state import (  # noqa: E402
    days_since_marker,
    now_iso,
    read_registry,
    read_state,
    state_dir,
    touch_marker,
    write_state,
)
from _activity import (  # noqa: E402
    observations_since_marker,
    outcomes_since_marker,
)

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


def _setup_logging(verbose: bool = False) -> None:
    from core.logging_os import setup as _logging_os_setup

    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    _logging_os_setup(level="debug" if verbose else "info")

    fmt = logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    fh = logging.handlers.RotatingFileHandler(
        _LOG_FILE, maxBytes=100_000, backupCount=10
    )
    fh.setFormatter(fmt)
    logging.getLogger().addHandler(fh)


logger = logging.getLogger("codingos.scheduled.nightly")


# ---------------------------------------------------------------------------
# Schema guard
# ---------------------------------------------------------------------------

def _schema_ok(db_path: Path) -> bool:
    try:
        with sqlite3.connect(str(db_path), timeout=5) as conn:
            row = conn.execute(
                "SELECT MAX(version) FROM schema_version"
            ).fetchone()
            if row and row[0] is not None:
                return int(row[0]) >= _SCHEMA_VERSION_MIN
            return False
    except sqlite3.Error as exc:
        logger.debug("schema check failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Task: decay
# ---------------------------------------------------------------------------

def _run_decay(db_path: Path, project_root: Path, *, dry_run: bool) -> dict:
    """Run confidence decay, flock-protected against session_enrich race."""
    marker = project_root / ".coding-os" / ".last-decay"
    lock_path = marker.with_suffix(".lock")

    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with open(lock_path, "w") as lock_f:
            try:
                fcntl.flock(lock_f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return {"status": "skipped", "reason": "lock_contention"}

            try:
                age = days_since_marker(marker)
                if age is not None and age < _DECAY_THROTTLE_DAYS:
                    return {
                        "status": "skipped",
                        "reason": f"ran {age:.1f}d ago (threshold {_DECAY_THROTTLE_DAYS}d)",
                    }

                if dry_run:
                    return {"status": "dry_run", "would_run": True, "marker_age_days": age}

                from decay import run_decay as do_decay  # noqa: PLC0415

                result = do_decay(db_path)
                touch_marker(marker)
                return {"status": "ok", **result}
            finally:
                fcntl.flock(lock_f, fcntl.LOCK_UN)

    except OSError as exc:
        logger.warning("decay task os error: %s", exc)
        return {"status": "error", "error": str(exc)}
    except ImportError as exc:
        logger.warning("decay task import error (decay.py missing?): %s", exc)
        return {"status": "error", "error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        logger.warning("decay task unexpected error: %s", exc)
        return {"status": "error", "error": str(exc)}


# ---------------------------------------------------------------------------
# Task: learn_extract
# ---------------------------------------------------------------------------

def _run_learn_extract(db_path: Path, project_root: Path, *, dry_run: bool) -> dict:
    """Mine patterns from task_outcomes; gated on new outcomes since last run."""
    marker = state_dir(project_root) / ".last-extract"

    new_outcomes = outcomes_since_marker(db_path, marker)
    if new_outcomes == 0:
        return {"status": "skipped", "reason": "no_new_outcomes"}

    try:
        with sqlite3.connect(str(db_path), timeout=10) as conn:
            conn.row_factory = sqlite3.Row
            total = conn.execute("SELECT COUNT(*) FROM task_outcomes").fetchone()[0]
            if total < _MIN_OUTCOMES:
                return {
                    "status": "skipped",
                    "reason": f"insufficient_data (need {_MIN_OUTCOMES}, have {total})",
                }

    except sqlite3.Error as exc:
        return {"status": "error", "error": str(exc)}

    if dry_run:
        return {"status": "dry_run", "would_run": True, "new_outcomes": new_outcomes}

    try:
        from tools.learning import learn_extract  # noqa: PLC0415

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
    except Exception as exc:  # noqa: BLE001
        logger.warning("learn_extract unexpected error: %s", exc)
        return {"status": "error", "error": str(exc)}


# ---------------------------------------------------------------------------
# Task: routing_recalc
# ---------------------------------------------------------------------------

def _run_routing_recalc(db_path: Path, *, dry_run: bool) -> dict:
    """Recalculate routing weights if drift detected."""
    try:
        from tools.routing import recalculate_weights, routing_drift  # noqa: PLC0415

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
    except Exception as exc:  # noqa: BLE001
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
        run["tasks"]["all"] = {"status": "skipped", "reason": f"schema_version < {_SCHEMA_VERSION_MIN}"}
        logger.warning("[%s] schema too old — skip all", slug)
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
        t = _run_decay(db_path, project_root, dry_run=dry_run)
        run["tasks"]["decay"] = t
        logger.info("[%s] decay → %s", slug, t.get("status"))
        if t.get("status") == "error":
            errors += 1
    except Exception as exc:  # noqa: BLE001
        run["tasks"]["decay"] = {"status": "error", "error": str(exc)}
        logger.error("[%s] decay raised: %s", slug, exc)
        errors += 1

    # Task 2: learn_extract
    try:
        t = _run_learn_extract(db_path, project_root, dry_run=dry_run)
        run["tasks"]["learn_extract"] = t
        logger.info("[%s] learn_extract → %s", slug, t.get("status"))
        if t.get("status") == "error":
            errors += 1
    except Exception as exc:  # noqa: BLE001
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
    except Exception as exc:  # noqa: BLE001
        run["tasks"]["routing_recalc"] = {"status": "error", "error": str(exc)}
        logger.error("[%s] routing_recalc raised: %s", slug, exc)
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
        except Exception as exc:  # noqa: BLE001
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

    errors_total = sum(
        1 for r in results if r.get("last_error") or r.get("error")
    )
    return 1 if errors_total > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
