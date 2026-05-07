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

import logging
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure db module is importable
sys.path.insert(0, str(Path(__file__).resolve().parent))

from database import DEFAULT_DB_PATH, get_connection, get_schema_version

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
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


def run_decay(db_path: str | Path | None = None, *, dry_run: bool = False) -> dict:
    """Run confidence decay on all learned_patterns.

    Args:
        db_path: Path to SQLite DB. Defaults to DEFAULT_DB_PATH.
        dry_run: If True, compute but don't write changes.

    Returns:
        Dict with stats: total_patterns, decayed, archived, unchanged, working_memory_cleaned.
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
        }

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
                    conn.execute(
                        "UPDATE learned_patterns SET promoted_to = 'archived' WHERE id = ?",
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
        "Summary: %d patterns processed, %d decayed, %d archived, %d unchanged, %d working memory cleaned",
        stats["total_patterns"],
        stats["decayed"],
        stats["archived"],
        stats["unchanged"],
        stats["working_memory_cleaned"],
    )


if __name__ == "__main__":
    main()
