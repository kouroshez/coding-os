"""cos_route_skill — skill recommendation from historical task outcomes.

Which skills to load is a different question from which model to run, and the
two evolve on their own schedules; keeping them apart stops a skill-policy edit
from touching the model router. A leaf apart from the shared statistics.
"""

from __future__ import annotations

import logging
import sqlite3

from ._routing_stats import COLD_START_THRESHOLD, _data_confidence

logger = logging.getLogger("thinking_os.routing")

# Cold-start skill defaults per domain — core routing POLICY data, not a cli
# literal (Rule 11 is cli-scoped); the warm path overrides these from real
# task_outcomes. Making cold-start data-driven from the consumer's installed
# stacks is a deferred enhancement (TASK-441/F13).
DEFAULT_SKILLS = {
    "BACKEND": ["python-django"],
    "FRONTEND": ["nextjs-react"],
    "INFRA": ["shell-scripting"],  # was 'bash-linux' — a dangling, non-existent skill
    "DOCS": [],
}


def route_skill(
    conn: sqlite3.Connection,
    *,
    domain: str,
    task_type: str | None = None,
    complexity: str | None = None,
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
                {"name": s, "confidence": 0.0, "reason": "static_default"} for s in static_skills
            ],
            "fallback_source": "skill-enforcement.md",
            "data_points": total,
        }

    # Query historically successful skills
    conditions = [
        "domain = ?",
        "outcome = 'success'",
        "skills_used IS NOT NULL",
        "skills_used != ''",
    ]
    params: list = [domain]
    if task_type:
        conditions.append("type = ?")
        params.append(task_type)
    if complexity:
        conditions.append("complexity = ?")
        params.append(complexity)
    where = " AND ".join(conditions)

    rows = conn.execute(
        f"SELECT skills_used, COUNT(*) AS success_count "
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
        skills.append(
            {
                "name": skill_name,
                "confidence": round(_data_confidence(total) * rate, 2),
                "reason": f"data_driven ({d['success_count']} successes in {domain})",
            }
        )

    # Add static defaults if not already present
    for s in static_skills:
        if s not in seen_names:
            skills.append(
                {
                    "name": s,
                    "confidence": 0.0,
                    "reason": "static_default",
                }
            )

    return {
        "skills": skills,
        "fallback_source": "skill-enforcement.md" if not rows else "data_driven",
        "data_points": total,
    }
