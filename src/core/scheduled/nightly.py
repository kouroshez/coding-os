#!/usr/bin/env python3
"""
Coding OS — Nightly maintenance script (CRON A).

Runs per-project: decay · learn_extract · routing_recalc.
Each task is independently gated and recorded in last_run.json.

Module layout:
    _nightly_memory  decay, learn_extract, routing_recalc, digest, sweeps, gc
    _nightly_board   board coherence, reclaim, dependency reconcile
    _nightly_index   doc chunk reconcile, stale graph reindex
    this module      per-project orchestration + the CLI entry point

See docs/engineering/scheduled-jobs.md for full contract.
"""

from __future__ import annotations

import argparse
import json
import logging
import logging.handlers
import sqlite3
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrap: make the src/core packages importable when run as a file
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve().parent
_CORE = _HERE.parent
_SRC = _CORE.parent
_THINKING_OS = _CORE / "thinking_os"
for _bootstrap_path in (_SRC, _CORE, _THINKING_OS):
    if str(_bootstrap_path) not in sys.path:
        sys.path.insert(0, str(_bootstrap_path))

from scheduled._nightly_board import (  # noqa: E402
    _run_board_coherence,
    _run_dep_reconcile,
    _run_reclaim,
)
from scheduled._nightly_index import (  # noqa: E402
    _run_doc_reconcile,
    _run_graph_reindex_if_stale,
)
from scheduled._nightly_memory import (  # noqa: E402
    _run_decay,
    _run_digest,
    _run_error_sweep,
    _run_learn_extract,
    _run_memory_gc,
    _run_routing_recalc,
)
from scheduled._state import (  # noqa: E402
    now_iso,
    read_registry,
    read_state,
    write_state,
)
from scheduled.config import load_config  # noqa: E402

# ---------------------------------------------------------------------------
# Logging — global rotating log + stderr for foreground runs
# ---------------------------------------------------------------------------

_LOG_DIR = Path.home() / ".coding-os" / "scheduled"
_LOG_FILE = _LOG_DIR / "nightly.log"
_MAX_CONSECUTIVE_FAILURES = 3
_SCHEMA_VERSION_MIN = 7


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
    # unauthored and long-blocked tasks across the whole graph.
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

    # Task 5: doc_reconcile (prune chunks for deleted docs)
    try:
        t = _run_doc_reconcile(db_path, project_root, dry_run=dry_run)
        run["tasks"]["doc_reconcile"] = t
        logger.info("[%s] doc_reconcile → %s", slug, t.get("status"))
        if t.get("status") == "error":
            errors += 1
    except Exception as exc:
        run["tasks"]["doc_reconcile"] = {"status": "error", "error": str(exc)}
        logger.error("[%s] doc_reconcile raised: %s", slug, exc)
        errors += 1

    # Task 6: memory_gc (orphan embeddings + trash observations)
    try:
        t = _run_memory_gc(db_path, dry_run=dry_run)
        run["tasks"]["memory_gc"] = t
        logger.info("[%s] memory_gc → %s", slug, t.get("status"))
        if t.get("status") == "error":
            errors += 1
    except Exception as exc:
        run["tasks"]["memory_gc"] = {"status": "error", "error": str(exc)}
        logger.error("[%s] memory_gc raised: %s", slug, exc)
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
