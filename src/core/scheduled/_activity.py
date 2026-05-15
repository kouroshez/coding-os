"""Activity detection helpers for scheduled jobs."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger("codingos.scheduled.activity")


def activity_since(db_path: Path | str, *, days: float = 1.0) -> dict:
    """Return recent activity counts from observations + task_outcomes.

    Args:
        db_path: Path to project coding-os.db.
        days: Look-back window in days.

    Returns:
        {obs_count, outcome_count, last_obs_at, last_outcome_at, has_activity}
    """
    result: dict = {
        "obs_count": 0,
        "outcome_count": 0,
        "last_obs_at": None,
        "last_outcome_at": None,
        "has_activity": False,
    }
    db_path = Path(db_path)
    if not db_path.exists():
        return result

    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    try:
        with sqlite3.connect(str(db_path), timeout=5) as conn:
            conn.row_factory = sqlite3.Row

            obs = conn.execute(
                "SELECT COUNT(*) AS cnt, MAX(created_at) AS last_at "
                "FROM observations WHERE created_at >= ?",
                (cutoff,),
            ).fetchone()
            if obs:
                result["obs_count"] = obs["cnt"] or 0
                result["last_obs_at"] = obs["last_at"]

            out = conn.execute(
                "SELECT COUNT(*) AS cnt, MAX(created_at) AS last_at "
                "FROM task_outcomes WHERE created_at >= ?",
                (cutoff,),
            ).fetchone()
            if out:
                result["outcome_count"] = out["cnt"] or 0
                result["last_outcome_at"] = out["last_at"]

    except sqlite3.Error as exc:
        logger.debug("activity_since db error for %s: %s", db_path, exc)
    except OSError as exc:
        logger.debug("activity_since os error for %s: %s", db_path, exc)

    result["has_activity"] = (
        result["obs_count"] > 0 or result["outcome_count"] > 0
    )
    return result


def outcomes_since_marker(db_path: Path | str, marker_path: Path | str) -> int:
    """Count task_outcomes added since marker file was last written."""
    marker_path = Path(marker_path)
    db_path = Path(db_path)
    if not db_path.exists():
        return 0

    cutoff = None
    if marker_path.exists():
        try:
            mtime = marker_path.stat().st_mtime
            # SQLite datetime('now') stores "YYYY-MM-DD HH:MM:SS" without tz;
            # use same format for the cutoff so string comparison is correct.
            cutoff = datetime.fromtimestamp(mtime, tz=timezone.utc).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        except OSError as exc:
            logger.debug("outcomes_since_marker marker read error: %s", exc)

    try:
        with sqlite3.connect(str(db_path), timeout=5) as conn:
            if cutoff:
                row = conn.execute(
                    "SELECT COUNT(*) FROM task_outcomes WHERE created_at >= ?",
                    (cutoff,),
                ).fetchone()
            else:
                row = conn.execute("SELECT COUNT(*) FROM task_outcomes").fetchone()
            return row[0] if row else 0
    except sqlite3.Error as exc:
        logger.debug("outcomes_since_marker db error: %s", exc)
        return 0


def observations_since_marker(db_path: Path | str, marker_path: Path | str) -> int:
    """Count observations added since marker file was last written."""
    marker_path = Path(marker_path)
    db_path = Path(db_path)
    if not db_path.exists():
        return 0

    cutoff = None
    if marker_path.exists():
        try:
            mtime = marker_path.stat().st_mtime
            cutoff = datetime.fromtimestamp(mtime, tz=timezone.utc).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        except OSError as exc:
            logger.debug("observations_since_marker marker read error: %s", exc)

    try:
        with sqlite3.connect(str(db_path), timeout=5) as conn:
            if cutoff:
                row = conn.execute(
                    "SELECT COUNT(*) FROM observations WHERE created_at >= ?",
                    (cutoff,),
                ).fetchone()
            else:
                row = conn.execute("SELECT COUNT(*) FROM observations").fetchone()
            return row[0] if row else 0
    except sqlite3.Error as exc:
        logger.debug("observations_since_marker db error: %s", exc)
        return 0
