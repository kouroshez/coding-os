"""routing_weights — the rebuild and the staleness check over it.

Both functions own the same table: one writes it from task_outcomes, the other
reports how far behind it has fallen. They change together and share the
thresholds, so they live together and nothing else needs to know the schema.
"""

from __future__ import annotations

import contextlib
import logging
import sqlite3

logger = logging.getLogger("thinking_os.routing")

WEIGHT_USE_THRESHOLD = 20  # minimum samples before weights influence routing
WEIGHT_STORE_THRESHOLD = 5  # minimum samples to store a weight

_STALE_THRESHOLD = 15  # new outcomes since last recalc before drift is flagged


def recalculate_weights(conn: sqlite3.Connection) -> dict:
    """Rebuild routing_weights from task_outcomes aggregation.

    Args:
        conn: SQLite connection.

    Returns:
        Dict with count of weights recalculated.
    """
    # The recalc SQL below is intentionally duplicated in
    # src/core/hooks/_helpers/routing_evolution.py::_recalculate — the
    # import-light copy the session-start hook runs (it must NOT import this MCP
    # tool tree, Rule 8). Keep both in lockstep: a routing_weights schema change
    # lands in BOTH. routing_weights is rebuilt here but is NOT yet read by
    # route_model/route_skill (they rank task_outcomes directly); its consumer is
    # the deferred multi-model cost-aware ranker (audit RAPTOR-1).
    # Check if routing_weights table exists
    table_check = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='routing_weights'"
    ).fetchone()
    if not table_check:
        return {"status": "skipped", "reason": "routing_weights table not found (run migration v3)"}

    rows = conn.execute(
        "SELECT domain, complexity, model, skills_used AS skill, "
        "SUM(CASE WHEN outcome = 'success' THEN 1 ELSE 0 END) AS successes, "
        "COUNT(*) AS total "
        "FROM task_outcomes "
        "WHERE model IS NOT NULL "
        "GROUP BY domain, complexity, model, skills_used "
        "HAVING total >= ?",
        (WEIGHT_STORE_THRESHOLD,),
    ).fetchall()

    count = 0
    for row in rows:
        d = dict(row)
        rate = d["successes"] / d["total"] if d["total"] > 0 else 0
        conn.execute(
            "INSERT INTO routing_weights (domain, complexity, model, skill, success_rate, sample_count, last_updated) "
            "VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP) "
            "ON CONFLICT(domain, complexity, model, skill) DO UPDATE SET "
            "success_rate = ?, sample_count = ?, last_updated = CURRENT_TIMESTAMP",
            (
                d["domain"],
                d["complexity"],
                d["model"],
                d["skill"],
                round(rate, 4),
                d["total"],
                round(rate, 4),
                d["total"],
            ),
        )
        count += 1

    # Stamp staleness metadata (migration v26 columns; guard for older DBs)
    total_outcomes = conn.execute("SELECT COUNT(*) FROM task_outcomes").fetchone()[0]
    with contextlib.suppress(sqlite3.OperationalError):
        conn.execute(
            "UPDATE routing_weights SET last_recalc_at = CURRENT_TIMESTAMP, outcomes_at_recalc = ?",
            (total_outcomes,),
        )

    conn.commit()
    return {"status": "ok", "weights_updated": count, "outcomes_stamped": total_outcomes}


def routing_drift(conn: sqlite3.Connection) -> dict:
    """Detect whether routing_weights are stale relative to task_outcomes."""
    table_check = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='routing_weights'"
    ).fetchone()
    if not table_check:
        return {"drift_detected": False, "reason": "routing_weights table not found"}

    total = conn.execute("SELECT COUNT(*) FROM task_outcomes").fetchone()[0]

    last_recalc_at = None
    outcomes_at_recalc = 0
    try:
        row = conn.execute(
            "SELECT MAX(outcomes_at_recalc) AS at_recalc, "
            "       MAX(last_recalc_at) AS recalc_at "
            "FROM routing_weights"
        ).fetchone()
        if row:
            outcomes_at_recalc = row["at_recalc"] or 0
            last_recalc_at = row["recalc_at"]
    except sqlite3.OperationalError:
        # v26 columns not yet applied — use last_updated as proxy
        row = conn.execute("SELECT MAX(last_updated) AS recalc_at FROM routing_weights").fetchone()
        if row:
            last_recalc_at = row["recalc_at"]

    new_since_recalc = total - outcomes_at_recalc
    drift = new_since_recalc >= _STALE_THRESHOLD

    return {
        "drift_detected": drift,
        "new_outcomes_since_recalc": new_since_recalc,
        "threshold": _STALE_THRESHOLD,
        "last_recalc_at": last_recalc_at,
        "recommendation": "recalculate" if drift else "ok",
    }
