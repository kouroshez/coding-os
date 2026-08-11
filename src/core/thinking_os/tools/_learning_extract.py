"""cos_learn_extract — mine recurring patterns out of recorded task outcomes.

One pass over `task_outcomes` plus the friction, hook-block and commit signals,
upserting each finding as a `learned_patterns` row. Contract:
docs/engineering/learning-extraction.md.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3

logger = logging.getLogger("thinking_os.learning")

try:  # package import
    from ._learning_generalize import _collapse_duplicate_patterns, generalize_lessons
    from ._learning_mining import _mine_friction_lessons
    from ._learning_mining_logs import _mine_commit_lessons, _mine_hook_block_lessons
    from ._learning_store import _upsert_pattern
except ImportError:  # flat import
    from _learning_generalize import (  # type: ignore[no-redef,import-not-found]
        _collapse_duplicate_patterns,
        generalize_lessons,
    )
    from _learning_mining import _mine_friction_lessons  # type: ignore[no-redef,import-not-found]
    from _learning_mining_logs import (  # type: ignore[no-redef,import-not-found]
        _mine_commit_lessons,
        _mine_hook_block_lessons,
    )
    from _learning_store import _upsert_pattern  # type: ignore[no-redef,import-not-found]


MIN_DATA_THRESHOLD = 3  # minimum task outcomes before extraction


def learn_extract(
    conn: sqlite3.Connection,
    *,
    min_occurrences: int = 3,
) -> dict:
    """Scan task_outcomes to discover recurring patterns.

    Detects:
      - domain_rework: domains with high rework rates
      - skill_correlation: skills correlated with success/failure
      - complexity_mismatch: tasks classified too low/high

    Args:
        conn: SQLite connection.
        min_occurrences: Minimum occurrences to consider a pattern.

    Returns:
        Dict with extracted patterns and stats.
    """
    min_occurrences = max(1, min_occurrences)

    # Check data threshold
    total_outcomes = conn.execute("SELECT COUNT(*) FROM task_outcomes").fetchone()[0]
    if total_outcomes < MIN_DATA_THRESHOLD:
        return {
            "status": "insufficient_data",
            "message": f"Insufficient data (need {MIN_DATA_THRESHOLD}+ outcomes, have {total_outcomes})",
            "extracted": [],
        }

    extracted: list[dict] = []

    # Heal any legacy count-snapshot duplicates before mining so the upsert
    # below updates a single survivor row per fact.
    _collapse_duplicate_patterns(conn)

    # --- Domain rework patterns ---
    domain_rows = conn.execute(
        "SELECT domain, COUNT(*) AS total, "
        "SUM(CASE WHEN outcome = 'rework' THEN 1 ELSE 0 END) AS rework_count "
        "FROM task_outcomes "
        "GROUP BY domain "
        "HAVING rework_count >= ?",
        (min_occurrences,),
    ).fetchall()

    for row in domain_rows:
        d = dict(row)
        rework_rate = d["rework_count"] / d["total"] if d["total"] > 0 else 0
        if rework_rate < 0.2:
            continue  # not significant enough
        confidence = min(0.9, d["rework_count"] / (d["total"] * 2))
        pattern_text = (
            f"{d['domain']} domain has {rework_rate:.0%} rework rate "
            f"({d['rework_count']}/{d['total']} tasks)"
        )
        extracted.append(
            _upsert_pattern(
                conn,
                pattern=pattern_text,
                memory_type="pattern",
                domain=d["domain"],
                source="learn_extract",
                confidence=confidence,
                concepts=json.dumps([d["domain"].lower(), "rework", "domain_pattern"]),
            )
        )

    # --- Skill correlation patterns ---
    skill_rows = conn.execute(
        "SELECT skills_used, outcome, COUNT(*) AS count "
        "FROM task_outcomes "
        "WHERE skills_used IS NOT NULL AND skills_used != '' "
        "GROUP BY skills_used, outcome "
        "HAVING count >= ?",
        (min_occurrences,),
    ).fetchall()

    for row in skill_rows:
        d = dict(row)
        if d["outcome"] == "rework":
            confidence = min(0.9, d["count"] / 10.0)
            pattern_text = (
                f"Skill '{d['skills_used']}' correlates with rework ({d['count']} occurrences)"
            )
            extracted.append(
                _upsert_pattern(
                    conn,
                    pattern=pattern_text,
                    memory_type="pattern",
                    domain=None,
                    source="learn_extract",
                    confidence=confidence,
                    concepts=json.dumps(["skill", d["skills_used"], "rework"]),
                )
            )

    # --- Complexity mismatch patterns ---
    mismatch_rows = conn.execute(
        "SELECT complexity, outcome, COUNT(*) AS count "
        "FROM task_outcomes "
        "WHERE outcome = 'rework' "
        "GROUP BY complexity "
        "HAVING count >= ?",
        (min_occurrences,),
    ).fetchall()

    for row in mismatch_rows:
        d = dict(row)
        # Check if CLEAR tasks frequently rework (likely underclassified)
        if d["complexity"] == "CLEAR" and d["count"] >= min_occurrences:
            total_clear = conn.execute(
                "SELECT COUNT(*) FROM task_outcomes WHERE complexity = 'CLEAR'"
            ).fetchone()[0]
            if total_clear > 0:
                rate = d["count"] / total_clear
                if rate > 0.3:
                    confidence = min(0.9, rate)
                    pattern_text = (
                        f"CLEAR tasks rework at {rate:.0%} — may be underclassified "
                        f"({d['count']}/{total_clear})"
                    )
                    extracted.append(
                        _upsert_pattern(
                            conn,
                            pattern=pattern_text,
                            memory_type="decision",
                            domain=None,
                            source="learn_extract",
                            confidence=confidence,
                            concepts=json.dumps(["complexity", "classification", "mismatch"]),
                        )
                    )

    # --- Success baseline patterns (positive-signal mining) ---
    # A healthy success-only history must still yield learnable patterns —
    # without this the loop can ONLY learn from failure, so a project that
    # rarely reworks produces zero patterns forever. Mine per-domain and
    # per-skill success so cos_learn_suggest has positive anchors to rank.
    # Variance gate: a success-rate stat only informs when the corpus has a
    # non-success outcome to contrast against. On a monotone-success corpus
    # every "X succeeds 100%" is a tautology — skip both stat branches.
    # See docs/engineering/learning-extraction.md § Variance gate.
    _has_variance = (
        conn.execute("SELECT COUNT(*) FROM task_outcomes WHERE outcome != 'success'").fetchone()[0]
        > 0
    )

    success_domain_rows = (
        conn.execute(
            "SELECT domain, COUNT(*) AS total, "
            "SUM(CASE WHEN outcome = 'success' THEN 1 ELSE 0 END) AS success_count "
            "FROM task_outcomes WHERE domain IS NOT NULL AND domain != '' "
            "GROUP BY domain HAVING success_count >= ?",
            (min_occurrences,),
        ).fetchall()
        if _has_variance
        else []
    )
    for row in success_domain_rows:
        d = dict(row)
        rate = d["success_count"] / d["total"] if d["total"] else 0
        confidence = min(0.85, 0.4 + d["success_count"] / 20.0)
        pattern_text = (
            f"{d['domain']} domain succeeds at {rate:.0%} "
            f"({d['success_count']}/{d['total']} tasks) — reliable baseline"
        )
        extracted.append(
            _upsert_pattern(
                conn,
                pattern=pattern_text,
                # 'stat' (not a belief): a success rate is observability, not a
                # lesson — excluded from the digest + cos_learn_suggest so it
                # never masquerades as a learning. See learning-extraction.md.
                memory_type="stat",
                domain=d["domain"],
                source="learn_extract",
                confidence=confidence,
                concepts=json.dumps([d["domain"].lower(), "success", "baseline", "stat"]),
            )
        )

    skill_success_rows = (
        conn.execute(
            "SELECT skills_used, COUNT(*) AS count "
            "FROM task_outcomes "
            "WHERE outcome = 'success' AND skills_used IS NOT NULL AND skills_used != '' "
            "GROUP BY skills_used HAVING count >= ?",
            (min_occurrences,),
        ).fetchall()
        if _has_variance
        else []
    )
    for row in skill_success_rows:
        d = dict(row)
        confidence = min(0.8, 0.4 + d["count"] / 20.0)
        pattern_text = (
            f"Skill set '{d['skills_used']}' correlates with success ({d['count']} tasks)"
        )
        extracted.append(
            _upsert_pattern(
                conn,
                pattern=pattern_text,
                memory_type="stat",  # observability, not a belief — see above
                domain=None,
                source="learn_extract",
                confidence=confidence,
                concepts=json.dumps(["skill", "success", "correlation", "stat"]),
            )
        )

    # --- Failure anatomy patterns (v25) ---
    # Mine structured backtrack_events for recurring root_cause patterns.
    # Only runs when anatomy columns are present (migration v25).
    try:
        from tools.cognition import CANONICAL_REMEDIES

        anat_rows = conn.execute(
            # Anatomy pairs a recurring cause with its remedy — the one the agent
            # recorded, else the canonical corrective action for that cause. Never
            # a bare count (learning-extraction.md § Anatomy from backtracks).
            "SELECT root_cause, COUNT(*) AS cnt, "
            "       GROUP_CONCAT(DISTINCT from_formula) AS formulas, "
            "       MAX(corrective_action) AS remedy "
            "FROM backtrack_events "
            "WHERE root_cause IS NOT NULL "
            "GROUP BY root_cause "
            "HAVING cnt >= ?",
            (min_occurrences,),
        ).fetchall()
        for row in anat_rows:
            d = dict(row)
            remedy = (d["remedy"] or "").strip() or CANONICAL_REMEDIES.get(d["root_cause"], "")
            if not remedy:
                continue  # no recorded nor canonical remedy — skip, never a bare count
            confidence = min(0.85, d["cnt"] / 20.0 + 0.3)
            formulas_str = d["formulas"] or ""
            pattern_text = (
                f"Recurring backtrack root cause '{d['root_cause']}' "
                f"({d['cnt']} occurrences"
                + (f"; formulas: {formulas_str[:60]}" if formulas_str else "")
                + f") → {remedy[:160]}"
            )
            extracted.append(
                _upsert_pattern(
                    conn,
                    pattern=pattern_text,
                    memory_type="failure",
                    domain=None,
                    source="learn_extract",
                    confidence=confidence,
                    concepts=json.dumps(["failure", d["root_cause"], "backtrack"]),
                )
            )
    except Exception as exc:  # backtrack_events or anatomy columns absent — fire-and-forget
        logger.debug("learn_extract: failure anatomy skipped: %s", exc)

    # --- Friction lessons ---
    # The abundant, automatic learning signal: hook BLOCKs and tool failures
    # the agent emits every session. Mined into actionable
    # `lesson` patterns so the loop learns from mistakes — not just success
    # statistics. Contract: docs/engineering/learning-extraction.md.
    try:
        distill_budget = int(os.environ.get("COS_DISTILL_MAX_CLUSTERS", "20"))
    except ValueError:
        distill_budget = 20
    distill_state = {"remaining": max(0, distill_budget)}
    extracted.extend(
        _mine_friction_lessons(conn, min_occurrences=min_occurrences, distill_state=distill_state)
    )
    # Hook BLOCKs live in the activity log (not observations) on Claude — mine
    # them too so the richest friction signal becomes a lesson.
    extracted.extend(
        _mine_hook_block_lessons(conn, min_occurrences=min_occurrences, distill_state=distill_state)
    )
    # fix:/revert: commit subjects — the real engineering-lesson signal that
    # reasoning records in git history, not in any friction table (§5).
    extracted.extend(_mine_commit_lessons(conn, min_occurrences=min_occurrences))

    # Generalize related lessons into human-review drafts (B3). Fire-and-forget;
    # writes only when a NEW cluster forms (deduped). Never blocks extraction.
    try:
        generalize_lessons(conn)
    except Exception as exc:
        logger.debug("generalize_lessons skipped: %s", exc)

    conn.commit()
    return {
        "status": "ok",
        "total_outcomes_analyzed": total_outcomes,
        "extracted": extracted,
    }
