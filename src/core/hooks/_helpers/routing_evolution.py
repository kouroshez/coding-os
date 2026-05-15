"""Session startup helper — autonomous routing evolution check."""
from __future__ import annotations

import sqlite3
import sys

_STALE_THRESHOLD = 15
_WEIGHT_STORE_THRESHOLD = 5  # mirrors routing.py MIN_SAMPLES_PER_BUCKET


def _recalculate(conn: sqlite3.Connection) -> int:
    """Rebuild routing_weights from task_outcomes. Returns rows updated."""
    rows = conn.execute(
        "SELECT domain, complexity, model, skills_used AS skill, "
        "SUM(CASE WHEN outcome = 'success' THEN 1 ELSE 0 END) AS successes, "
        "COUNT(*) AS total "
        "FROM task_outcomes "
        "WHERE model IS NOT NULL "
        "GROUP BY domain, complexity, model, skills_used "
        "HAVING total >= ?",
        (_WEIGHT_STORE_THRESHOLD,),
    ).fetchall()

    count = 0
    for row in rows:
        rate = row[4] / row[5] if row[5] > 0 else 0.0
        conn.execute(
            "INSERT INTO routing_weights "
            "(domain, complexity, model, skill, success_rate, sample_count, last_updated) "
            "VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP) "
            "ON CONFLICT(domain, complexity, model, skill) DO UPDATE SET "
            "success_rate = ?, sample_count = ?, last_updated = CURRENT_TIMESTAMP",
            (row[0], row[1], row[2], row[3],
             round(rate, 4), row[5], round(rate, 4), row[5]),
        )
        count += 1

    total_outcomes = conn.execute("SELECT COUNT(*) FROM task_outcomes").fetchone()[0]
    try:
        conn.execute(
            "UPDATE routing_weights SET last_recalc_at = CURRENT_TIMESTAMP, "
            "outcomes_at_recalc = ?",
            (total_outcomes,),
        )
    except sqlite3.OperationalError:
        pass  # v26 columns not yet applied; recalc still succeeds

    conn.commit()
    return count


def main(argv: list[str]) -> int:
    if len(argv) < 2 or not argv[1]:
        return 0

    db_path = argv[1]
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        # Guard: both tables must exist
        for tbl in ("task_outcomes", "routing_weights"):
            if not conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (tbl,)
            ).fetchone():
                conn.close()
                return 0

        total = conn.execute("SELECT COUNT(*) FROM task_outcomes").fetchone()[0]

        outcomes_at_recalc = 0
        try:
            row = conn.execute(
                "SELECT MAX(outcomes_at_recalc) AS at_recalc FROM routing_weights"
            ).fetchone()
            outcomes_at_recalc = row["at_recalc"] or 0
        except sqlite3.OperationalError:
            pass  # v26 columns not yet applied — treat as cold start

        new_since_recalc = total - outcomes_at_recalc
        if new_since_recalc < _STALE_THRESHOLD:
            conn.close()
            return 0

        updated = _recalculate(conn)
        conn.close()

        if updated > 0:
            print(
                f"[Routing Evolution] Auto-refreshed routing weights "
                f"({updated} buckets, {new_since_recalc} new outcomes)"
            )

    except Exception:
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
