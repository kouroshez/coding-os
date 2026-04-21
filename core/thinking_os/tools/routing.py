"""
Thinking OS — MCP routing tools (TASK-145).

2 tools for data-driven model and skill selection:
  - cos_route_model: complexity → model recommendation
  - cos_route_skill: task context → skill recommendation
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Optional

logger = logging.getLogger("thinking_os.routing")

COLD_START_THRESHOLD = 10  # minimum outcomes before data-driven recommendations
MIN_SAMPLES_PER_BUCKET = 5  # minimum samples to recommend a specific model

# Static defaults from performance.md and skill-enforcement.md
DEFAULT_MODELS = {
    "CLEAR": "sonnet",
    "COMPLICATED": "sonnet",
    "COMPLEX": "opus",
    "CHAOTIC": "sonnet",
}

DEFAULT_SKILLS = {
    "BACKEND": ["python-django"],
    "FRONTEND": ["nextjs-react"],
    "INFRA": ["bash-linux"],
    "DOCS": [],
}


# ---------------------------------------------------------------------------
# cos_route_model
# ---------------------------------------------------------------------------

def route_model(
    conn: sqlite3.Connection,
    *,
    complexity: str,
    dimensions: int = 1,
    domain: Optional[str] = None,
) -> dict:
    """Recommend optimal model based on historical outcome data.

    Cold start (< 10 outcomes): returns static default.
    Warm: queries success rates per model for the given complexity+domain.

    Args:
        conn: SQLite connection.
        complexity: Cynefin classification (CLEAR/COMPLICATED/COMPLEX/CHAOTIC).
        dimensions: Number of dimensions.
        domain: Task domain (e.g. "BACKEND").

    Returns:
        Dict with recommended_model, confidence, reason, fallback_model.
    """
    fallback = DEFAULT_MODELS.get(complexity, "sonnet")

    # Check data volume
    total = conn.execute("SELECT COUNT(*) FROM task_outcomes").fetchone()[0]

    if total < COLD_START_THRESHOLD:
        return {
            "recommended_model": fallback,
            "confidence": 0.0,
            "reason": "Cold start — using default from performance.md",
            "fallback_model": fallback,
            "data_points": total,
        }

    # Query success rates per model for this complexity
    conditions = ["complexity = ?"]
    params: list = [complexity]
    if domain:
        conditions.append("domain = ?")
        params.append(domain)
    where = " AND ".join(conditions)

    rows = conn.execute(
        f"SELECT model, "  # noqa: S608
        "SUM(CASE WHEN outcome = 'success' THEN 1 ELSE 0 END) AS successes, "
        "COUNT(*) AS total "
        f"FROM task_outcomes WHERE {where} AND model IS NOT NULL "
        "GROUP BY model "
        "HAVING total >= ?",
        params + [MIN_SAMPLES_PER_BUCKET],
    ).fetchall()

    if not rows:
        return {
            "recommended_model": fallback,
            "confidence": 0.0,
            "reason": f"Insufficient data for {complexity}"
                      + (f" {domain}" if domain else "")
                      + f" (need {MIN_SAMPLES_PER_BUCKET}+ per model)",
            "fallback_model": fallback,
            "data_points": total,
        }

    # Find best model by success rate
    best_model = fallback
    best_rate = 0.0
    best_total = 0
    model_stats = []

    for row in rows:
        d = dict(row)
        rate = d["successes"] / d["total"] if d["total"] > 0 else 0
        model_stats.append({
            "model": d["model"],
            "success_rate": round(rate, 2),
            "sample_size": d["total"],
        })
        if rate > best_rate:
            best_rate = rate
            best_model = d["model"]
            best_total = d["total"]

    # Confidence based on data volume
    confidence = _data_confidence(total)

    return {
        "recommended_model": best_model,
        "confidence": round(confidence, 2),
        "reason": (
            f"{best_model} has {best_rate:.0%} success rate for "
            f"{complexity}"
            + (f" {domain}" if domain else "")
            + f" tasks (n={best_total})"
        ),
        "fallback_model": fallback,
        "data_points": total,
        "model_stats": model_stats,
    }


# ---------------------------------------------------------------------------
# cos_route_skill
# ---------------------------------------------------------------------------

def route_skill(
    conn: sqlite3.Connection,
    *,
    domain: str,
    task_type: Optional[str] = None,
    complexity: Optional[str] = None,
) -> dict:
    """Recommend skills based on historical outcome data.

    Cold start: returns static defaults from skill-enforcement.md.
    Warm: augments with historically successful skills.

    Args:
        conn: SQLite connection.
        domain: Task domain (e.g. "BACKEND").
        task_type: Type of task (e.g. "feat", "fix").
        complexity: Cynefin classification.

    Returns:
        Dict with skills list and fallback source.
    """
    static_skills = DEFAULT_SKILLS.get(domain, [])

    total = conn.execute("SELECT COUNT(*) FROM task_outcomes").fetchone()[0]

    if total < COLD_START_THRESHOLD:
        return {
            "skills": [
                {"name": s, "confidence": 0.0, "reason": "static_default"}
                for s in static_skills
            ],
            "fallback_source": "skill-enforcement.md",
            "data_points": total,
        }

    # Query historically successful skills
    conditions = ["domain = ?", "outcome = 'success'", "skills_used IS NOT NULL", "skills_used != ''"]
    params: list = [domain]
    if task_type:
        conditions.append("type = ?")
        params.append(task_type)
    if complexity:
        conditions.append("complexity = ?")
        params.append(complexity)
    where = " AND ".join(conditions)

    rows = conn.execute(
        f"SELECT skills_used, COUNT(*) AS success_count "  # noqa: S608
        f"FROM task_outcomes WHERE {where} "
        "GROUP BY skills_used "
        "ORDER BY success_count DESC LIMIT 10",
        params,
    ).fetchall()

    # Total for this domain to compute rates
    total_domain = conn.execute(
        "SELECT COUNT(*) FROM task_outcomes WHERE domain = ?", (domain,)
    ).fetchone()[0]

    skills: list[dict] = []
    seen_names: set[str] = set()

    # Add data-driven skills
    for row in rows:
        d = dict(row)
        skill_name = d["skills_used"]
        if skill_name in seen_names:
            continue
        seen_names.add(skill_name)
        rate = d["success_count"] / total_domain if total_domain > 0 else 0
        skills.append({
            "name": skill_name,
            "confidence": round(_data_confidence(total) * rate, 2),
            "reason": f"data_driven ({d['success_count']} successes in {domain})",
        })

    # Add static defaults if not already present
    for s in static_skills:
        if s not in seen_names:
            skills.append({
                "name": s,
                "confidence": 0.0,
                "reason": "static_default",
            })

    return {
        "skills": skills,
        "fallback_source": "skill-enforcement.md" if not rows else "data_driven",
        "data_points": total,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Router weight recalculation (TASK-148)
# ---------------------------------------------------------------------------

WEIGHT_USE_THRESHOLD = 20  # minimum samples before weights influence routing
WEIGHT_STORE_THRESHOLD = 5  # minimum samples to store a weight


def recalculate_weights(conn: sqlite3.Connection) -> dict:
    """Rebuild routing_weights from task_outcomes aggregation.

    Args:
        conn: SQLite connection.

    Returns:
        Dict with count of weights recalculated.
    """
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
            (d["domain"], d["complexity"], d["model"], d["skill"],
             round(rate, 4), d["total"], round(rate, 4), d["total"]),
        )
        count += 1

    conn.commit()
    return {"status": "ok", "weights_updated": count}


def _data_confidence(total_outcomes: int) -> float:
    """Map data volume to confidence level.

    0-9:   0.0  (cold start)
    10-19: 0.1-0.4
    20-49: 0.4-0.7
    50+:   0.7-0.9
    """
    if total_outcomes < 10:
        return 0.0
    elif total_outcomes < 20:
        return 0.1 + (total_outcomes - 10) * 0.03
    elif total_outcomes < 50:
        return 0.4 + (total_outcomes - 20) * 0.01
    else:
        return min(0.9, 0.7 + (total_outcomes - 50) * 0.002)
