"""Nightly memory-maintenance legs — decay, learning, routing, digest, sweeps.

Each leg is independently gated on activity since its own marker, so a quiet
project costs one cheap check rather than a full recompute.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path

from scheduled._activity import outcomes_since_marker
from scheduled._state import state_dir, touch_marker

logger = logging.getLogger("codingos.scheduled.nightly")

_DECAY_THROTTLE_DAYS = 7
_MIN_OUTCOMES = 3
_CRON_B_OBS_THRESHOLD = 10


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


def _run_memory_gc(db_path: Path, *, dry_run: bool) -> dict:
    """memory_gc — reclaim orphan embeddings + concept-graph edges + trash
    observations (no FK/trigger covers embeddings when a source row is deleted)."""
    from thinking_os.memory_gc import gc_memory

    return gc_memory(db_path=db_path, dry_run=dry_run)
