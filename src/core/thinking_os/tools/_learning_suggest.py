"""cos_learn_suggest — rank stored patterns for the task the agent is starting.

Read-only over `learned_patterns` plus breakthrough narratives; the retrieval
half of the loop whose write half is `_learning_extract`.
"""

from __future__ import annotations

import logging
import sqlite3

logger = logging.getLogger("thinking_os.learning")


def learn_suggest(
    conn: sqlite3.Connection,
    *,
    domain: str | None = None,
    complexity: str | None = None,
    task_type: str | None = None,
    limit: int = 5,
) -> dict:
    """Return relevant patterns for the current task context.

    Includes spaced repetition: patterns at 0.2-0.4 confidence that
    were once validated get priority with "fading" label.

    Args:
        conn: SQLite connection.
        domain: Task domain (e.g. "BACKEND").
        complexity: Cynefin classification.
        task_type: Type of task (e.g. "feat", "fix").
        limit: Max suggestions (1-20, default 5).

    Returns:
        Dict with suggestions list.
    """
    limit = max(1, min(20, limit))
    suggestions: list[dict] = []

    # --- Active patterns (confidence > 0.3) ---
    # Exclude stats — a success-rate baseline is observability, never a
    # suggestion to act on. See docs/engineering/learning-extraction.md.
    conditions = [
        "confidence >= 0.3",
        "COALESCE(memory_type, '') != 'stat'",
        "promoted_to IS NULL",
    ]
    params: list = []
    if domain:
        conditions.append("(domain = ? OR domain IS NULL)")
        params.append(domain)
    where = " AND ".join(conditions)

    # Relevance boost: complexity + task_type used to be accepted
    # then ignored, so recall was relevance-blind. There is no per-pattern
    # complexity/task_type column, so we BOOST (never exclude) patterns whose
    # concepts/pattern text mention the term — a matching pattern outranks an
    # equally-confident non-match. Boost params bind first (SELECT precedes WHERE).
    boost_terms: list[str] = []
    boost_params: list = []
    for term in (complexity, task_type):
        if term:
            boost_terms.append(
                "(CASE WHEN LOWER(COALESCE(concepts,'')) LIKE ? "
                "OR LOWER(pattern) LIKE ? THEN 1 ELSE 0 END)"
            )
            like = f"%{term.lower()}%"
            boost_params += [like, like]
    relevance = " + ".join(boost_terms) if boost_terms else "0"

    active_rows = conn.execute(
        f"SELECT id, pattern, memory_type, domain, confidence, impact_score, "
        f"times_validated, times_violated, ({relevance}) AS relevance "
        f"FROM learned_patterns WHERE {where} "
        "ORDER BY relevance DESC, confidence DESC, impact_score DESC LIMIT ?",
        boost_params + params + [limit],
    ).fetchall()

    for row in active_rows:
        d = dict(row)
        suggestions.append(
            {
                "id": d["id"],
                "pattern": d["pattern"],
                "confidence": d["confidence"],
                "impact_score": d.get("impact_score", 0.5),
                "memory_type": d["memory_type"],
                "reason": "active",
            }
        )

    # --- Fading patterns (spaced repetition) ---
    fading_conditions = [
        "confidence BETWEEN 0.2 AND 0.4",
        # Established-ness (occurrence), not validation: after the honest
        # times_validated reset a "seen" pattern still resurfaces for review.
        "times_seen >= 1",
        "COALESCE(memory_type, '') != 'stat'",
        "promoted_to IS NULL",
    ]
    fading_params: list = []
    if domain:
        fading_conditions.append("(domain = ? OR domain IS NULL)")
        fading_params.append(domain)
    fading_where = " AND ".join(fading_conditions)

    fading_rows = conn.execute(
        f"SELECT id, pattern, memory_type, domain, confidence, impact_score, "
        f"times_validated, times_violated "
        f"FROM learned_patterns WHERE {fading_where} "
        "ORDER BY confidence ASC LIMIT 3",
        fading_params,
    ).fetchall()

    for row in fading_rows:
        d = dict(row)
        suggestions.insert(
            0,
            {  # fading patterns go first
                "id": d["id"],
                "pattern": d["pattern"],
                "confidence": d["confidence"],
                "impact_score": d.get("impact_score", 0.5),
                "memory_type": d["memory_type"],
                "reason": "fading",
            },
        )

    # --- Breakthrough narratives (high-value lessons from past struggles) ---
    try:
        bt_conditions = ["oh.is_breakthrough = 1", "oh.narrative_key_insight IS NOT NULL"]
        bt_params: list = []
        if domain:
            bt_conditions.append("t.domain = ?")
            bt_params.append(domain)
        bt_where = " AND ".join(bt_conditions)

        bt_rows = conn.execute(
            f"SELECT oh.task_id, oh.narrative_key_insight, oh.narrative_what_failed, "
            f"oh.previous_outcome, t.domain "
            f"FROM outcome_history oh "
            f"LEFT JOIN task_outcomes t ON oh.task_id = t.task_id "
            f"WHERE {bt_where} "
            "ORDER BY oh.created_at DESC LIMIT 3",
            bt_params,
        ).fetchall()

        for row in bt_rows:
            d = dict(row)
            insight = d["narrative_key_insight"] or ""
            failed = d.get("narrative_what_failed") or ""
            label = f"[Breakthrough] {insight}"
            if failed:
                label += f" (avoid: {failed[:60]})"
            suggestions.append(
                {
                    "id": None,
                    "pattern": label,
                    "confidence": 0.8,
                    "impact_score": 0.9,
                    "memory_type": "breakthrough",
                    "reason": f"breakthrough from {d['task_id']}",
                }
            )
    except Exception:
        pass  # outcome_history may not exist on pre-v4 DBs

    return {"suggestions": suggestions[:limit], "count": min(len(suggestions), limit)}
