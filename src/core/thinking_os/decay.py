#!/usr/bin/env python3
"""
Thinking OS — Confidence decay script (TASK-139).

Monthly batch process that applies Ebbinghaus exponential decay
to learned_patterns confidence. Run via `make thinking_os-decay`.

Features:
  - Exponential decay: conf * exp(-effective_rate * months)
  - Anti-forgetting: high-validation, high-impact, recently-accessed
  - Archive: patterns at floor (0.1) get promoted_to='archived'
  - Working memory cleanup: expired observations deleted
"""

from __future__ import annotations

import fcntl
import logging
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure db module is importable
sys.path.insert(0, str(Path(__file__).resolve().parent))

from database import DEFAULT_DB_PATH, get_connection, get_schema_version

from core.logging_os import setup as _logging_os_setup

_logging_os_setup(level="info")
logger = logging.getLogger("thinking_os.decay")

CONFIDENCE_FLOOR = 0.1


# ---------------------------------------------------------------------------
# Decay formulas
# ---------------------------------------------------------------------------


def effective_decay_rate(
    *,
    base_rate: float,
    times_validated: int,
    impact_score: float,
    last_accessed_days: float | None,
) -> float:
    """Calculate effective decay rate with anti-forgetting protections.

    Args:
        base_rate: Pattern's decay_rate column (default 0.1).
        times_validated: Number of successful validations.
        impact_score: Digital amygdala score (0.0-1.0).
        last_accessed_days: Days since last access (None if never accessed).

    Returns:
        Effective decay rate (may be 0.0 for recently-accessed patterns).
    """
    rate = base_rate

    # Deep encoding: frequently validated patterns decay 70% slower
    if times_validated >= 5:
        rate *= 0.3

    # Emotional tag: high-impact patterns decay 50% slower
    if impact_score >= 0.8:
        rate *= 0.5

    # Working memory refresh: recently accessed = skip decay
    if last_accessed_days is not None and last_accessed_days <= 7:
        rate = 0.0

    return rate


def decay_confidence(
    *,
    confidence: float,
    months_since_validated: float,
    eff_rate: float,
) -> float:
    """Apply Ebbinghaus exponential decay.

    Args:
        confidence: Current confidence value.
        months_since_validated: Months since last validation.
        eff_rate: Effective decay rate from effective_decay_rate().

    Returns:
        Decayed confidence, floored at 0.1.
    """
    if eff_rate <= 0.0 or months_since_validated <= 0.0:
        return confidence
    return max(CONFIDENCE_FLOOR, confidence * math.exp(-eff_rate * months_since_validated))


# ---------------------------------------------------------------------------
# Batch decay runner
# ---------------------------------------------------------------------------


def _days_since(dt_str: str | None) -> float | None:
    """Return days since a datetime string, or None if null."""
    if not dt_str:
        return None
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - dt
        return max(0.0, delta.total_seconds() / 86400.0)
    except (ValueError, TypeError):
        return None


def _marker_age_days(marker: Path) -> float | None:
    try:
        st = marker.stat()
    except OSError:
        return None
    return max(0.0, (datetime.now(timezone.utc).timestamp() - st.st_mtime) / 86400.0)


def run_decay_locked(
    db_path: str | Path,
    *,
    throttle_days: int = 7,
    archive_prune_days: int = 90,
    dry_run: bool = False,
    marker_path: Path | None = None,
) -> dict:
    """Throttled + flock-protected decay — the single entry point shared by the
    nightly job, the session_enrich Stop hook, and auto-brain-decay so they never
    double-decay (one mtime-throttled marker) or race (one exclusive lock). The
    throttle is mtime-based, so the marker file's content format is irrelevant.
    Marker defaults to ``<db-dir>/.last-decay`` (project-shared, next to the DB)."""
    path = Path(db_path).resolve()
    marker = marker_path or (path.parent / ".last-decay")
    lock_path = marker.with_suffix(".lock")
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.warning("decay lock dir error: %s", exc)
        return {"status": "error", "error": str(exc)}
    with open(lock_path, "w") as lock_f:
        try:
            fcntl.flock(lock_f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {"status": "skipped", "reason": "lock_contention"}
        try:
            age = _marker_age_days(marker)
            if age is not None and age < throttle_days:
                return {"status": "skipped", "reason": f"ran {age:.1f}d ago (threshold {throttle_days}d)"}
            if dry_run:
                return {"status": "dry_run", "would_run": True, "marker_age_days": age}
            result = run_decay(path, archive_prune_days=archive_prune_days)
            try:
                marker.write_text(datetime.now(timezone.utc).isoformat())
            except OSError:
                pass
            return {"status": "ok", **result}
        finally:
            fcntl.flock(lock_f, fcntl.LOCK_UN)


def run_decay(
    db_path: str | Path | None = None,
    *,
    dry_run: bool = False,
    archive_prune_days: int = 90,
) -> dict:
    """Run confidence decay + consolidation on all learned_patterns.

    Args:
        db_path: Path to SQLite DB. Defaults to DEFAULT_DB_PATH.
        dry_run: If True, compute but don't write changes.
        archive_prune_days: Hard-delete archived, at-floor, lightly-validated
            patterns not accessed within this window — caps unbounded growth
            without touching deeply-validated (times_validated>=5) memory.

    Returns:
        Dict with stats: total_patterns, decayed, archived, unchanged,
        working_memory_cleaned, merged, pruned.
    """
    path = Path(db_path or DEFAULT_DB_PATH)

    if not path.exists():
        logger.info("No DB found at %s, skipping decay", path)
        return {"status": "no_db", "message": f"No DB found at {path}"}

    conn = get_connection(path)
    try:
        stats = {
            "total_patterns": 0,
            "decayed": 0,
            "archived": 0,
            "unchanged": 0,
            "working_memory_cleaned": 0,
            "merged": 0,
            "pruned": 0,
        }

        # --- Prune long-dead archived patterns (caps unbounded growth) ---
        # Runs BEFORE this run's archiving so a freshly-archived pattern gets a
        # full grace window. Targets only patterns archived in a PRIOR run that
        # are at-floor, lightly-validated, and dormant (no access / validation /
        # creation within archive_prune_days). Deeply-validated patterns
        # (times_validated>=5) survive even when archived — they may resurface.
        if not dry_run:
            # Grace window is time-since-archived (archived_at). Legacy rows archived
            # before v33 have NULL archived_at → fall back to the old COALESCE date so
            # they stay prunable; new rows get a real archive_prune_days grace.
            pruned = conn.execute(
                "DELETE FROM learned_patterns "
                "WHERE promoted_to = 'archived' "
                "AND confidence <= ? "
                "AND COALESCE(times_validated, 0) < 5 "
                "AND COALESCE(archived_at, last_accessed_at, last_validated, created_at) "
                "    < datetime('now', ?)",
                (CONFIDENCE_FLOOR + 0.001, f"-{int(archive_prune_days)} days"),
            )
            stats["pruned"] = pruned.rowcount

        # --- Decay learned_patterns ---
        rows = conn.execute(
            "SELECT id, confidence, decay_rate, impact_score, times_validated, "
            "last_validated, last_accessed_at "
            "FROM learned_patterns WHERE promoted_to IS NULL OR promoted_to != 'archived'"
        ).fetchall()

        stats["total_patterns"] = len(rows)

        for row in rows:
            d = dict(row)
            days_validated = _days_since(d["last_validated"])
            days_accessed = _days_since(d["last_accessed_at"])

            months = (days_validated or 999.0) / 30.0

            eff_rate = effective_decay_rate(
                base_rate=d["decay_rate"] or 0.1,
                times_validated=d["times_validated"] or 0,
                impact_score=d["impact_score"] or 0.5,
                last_accessed_days=days_accessed,
            )

            new_conf = decay_confidence(
                confidence=d["confidence"],
                months_since_validated=months,
                eff_rate=eff_rate,
            )

            if abs(new_conf - d["confidence"]) < 0.001:
                stats["unchanged"] += 1
                continue

            if not dry_run:
                conn.execute(
                    "UPDATE learned_patterns SET confidence = ? WHERE id = ?",
                    (round(new_conf, 4), d["id"]),
                )

            # Archive if at floor
            if new_conf <= CONFIDENCE_FLOOR + 0.001:
                if not dry_run:
                    # Stamp archived_at only on first archival (COALESCE keeps the
                    # original) so the prune grace window measures time-since-archived.
                    conn.execute(
                        "UPDATE learned_patterns SET promoted_to = 'archived', "
                        "archived_at = COALESCE(archived_at, CURRENT_TIMESTAMP) "
                        "WHERE id = ?",
                        (d["id"],),
                    )
                stats["archived"] += 1
            else:
                stats["decayed"] += 1

        # --- Clean expired working memory ---
        if not dry_run:
            cursor = conn.execute(
                "DELETE FROM observations "
                "WHERE memory_type = 'working' AND expires_at IS NOT NULL AND expires_at < CURRENT_TIMESTAMP"
            )
            stats["working_memory_cleaned"] = cursor.rowcount

        # --- Consolidate: merge exact (pattern, domain) duplicates ---
        # learn_extract upserts by (pattern, domain), so dups are rare — this
        # is defensive: fold losers' access_count/times_validated into the
        # highest-confidence keeper so no signal is lost, then delete them.
        dup_groups = conn.execute(
            "SELECT pattern, COALESCE(domain, '') AS dom FROM learned_patterns "
            "GROUP BY pattern, COALESCE(domain, '') HAVING COUNT(*) > 1"
        ).fetchall()
        for g in dup_groups:
            members = conn.execute(
                "SELECT id, access_count, times_validated FROM learned_patterns "
                "WHERE pattern = ? AND COALESCE(domain, '') = ? "
                "ORDER BY confidence DESC, id DESC",
                (g["pattern"], g["dom"]),
            ).fetchall()
            losers = members[1:]
            if not losers:
                continue
            if not dry_run:
                conn.execute(
                    "UPDATE learned_patterns SET "
                    "access_count = COALESCE(access_count, 0) + ?, "
                    "times_validated = COALESCE(times_validated, 0) + ? WHERE id = ?",
                    (
                        sum((m["access_count"] or 0) for m in losers),
                        sum((m["times_validated"] or 0) for m in losers),
                        members[0]["id"],
                    ),
                )
                conn.executemany(
                    "DELETE FROM learned_patterns WHERE id = ?",
                    [(m["id"],) for m in losers],
                )
            stats["merged"] += len(losers)

        if not dry_run:
            conn.commit()

        return stats

    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    dry_run = "--dry-run" in sys.argv

    if dry_run:
        logger.info("DRY RUN — no changes will be written")

    stats = run_decay(dry_run=dry_run)
    logger.info("Decay results: %s", stats)

    if stats.get("status") == "no_db":
        sys.exit(0)

    logger.info(
        "Summary: %d patterns processed, %d decayed, %d archived, %d unchanged, "
        "%d working memory cleaned, %d merged, %d pruned",
        stats["total_patterns"],
        stats["decayed"],
        stats["archived"],
        stats["unchanged"],
        stats["working_memory_cleaned"],
        stats.get("merged", 0),
        stats.get("pruned", 0),
    )


if __name__ == "__main__":
    main()
