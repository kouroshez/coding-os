"""failure_pattern_query — aggregate structured failure anatomy.

Reads backtrack_events, not task_outcomes: a different table, a different
migration history, and a different consumer (the retro/diagnose surface) than
the routers. A leaf — it imports no sibling tool module.
"""

from __future__ import annotations

import logging
import sqlite3

logger = logging.getLogger("thinking_os.routing")

_VALID_ROOT_CAUSES = frozenset(
    {
        "wrong_model",
        "scope_too_large",
        "missing_context",
        "tool_failure",
        "spec_ambiguity",
        "env_mismatch",
        "other",
    }
)


def failure_pattern_query(
    conn: sqlite3.Connection,
    *,
    root_cause: str | None = None,
    domain: str | None = None,
    limit: int = 10,
) -> dict:
    """Aggregate structured failure anatomy from backtrack_events."""
    table_check = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='backtrack_events'"
    ).fetchone()
    if not table_check:
        return {
            "patterns": [],
            "total_structured": 0,
            "total_backtrack": 0,
            "note": "backtrack_events table not found",
        }

    # Check if anatomy columns exist (v25)
    try:
        conn.execute("SELECT root_cause FROM backtrack_events LIMIT 0")
        has_anatomy = True
    except sqlite3.OperationalError:
        has_anatomy = False

    total_backtrack = conn.execute("SELECT COUNT(*) FROM backtrack_events").fetchone()[0]

    if not has_anatomy:
        return {
            "patterns": [],
            "total_structured": 0,
            "total_backtrack": total_backtrack,
            "note": "failure anatomy columns not yet available (run migration v25)",
        }

    total_structured = conn.execute(
        "SELECT COUNT(*) FROM backtrack_events WHERE root_cause IS NOT NULL"
    ).fetchone()[0]

    limit = max(1, min(50, int(limit)))

    params: list = []
    where_clauses = ["root_cause IS NOT NULL"]
    if root_cause and root_cause in _VALID_ROOT_CAUSES:
        where_clauses.append("root_cause = ?")
        params.append(root_cause)

    where_sql = " AND ".join(where_clauses)

    agg_rows = conn.execute(
        f"SELECT root_cause, COUNT(*) AS cnt "
        f"FROM backtrack_events "
        f"WHERE {where_sql} "
        f"GROUP BY root_cause "
        f"ORDER BY cnt DESC "
        f"LIMIT ?",
        [*params, limit],
    ).fetchall()

    patterns = []
    for agg in agg_rows:
        rc = agg["root_cause"]
        # Fetch example entries for this root_cause
        ex_params: list = [rc]
        ex_where = "root_cause = ?"
        if domain:
            # backtrack_events has no domain column — filter via from_formula
            pass  # domain filter not applicable here
        examples_rows = conn.execute(
            f"SELECT from_formula, to_formula, reason, hypothesis, failure_signal, "
            f"       corrective_action, ts "
            f"FROM backtrack_events "
            f"WHERE {ex_where} "
            f"ORDER BY ts DESC LIMIT 3",
            ex_params,
        ).fetchall()
        examples = [dict(r) for r in examples_rows]
        patterns.append(
            {
                "root_cause": rc,
                "count": agg["cnt"],
                "examples": examples,
            }
        )

    return {
        "patterns": patterns,
        "total_structured": total_structured,
        "total_backtrack": total_backtrack,
    }
