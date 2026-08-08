"""
Thinking OS — MCP routing tools (TASK-145).

Tools for data-driven model and skill selection, failure pattern analysis,
and autonomous routing evolution:
  - cos_route_model: complexity → model recommendation
  - cos_route_skill: task context → skill recommendation
  - failure_pattern_query: aggregate structured failure anatomy
  - routing_drift: detect stale routing weights vs. current outcome patterns
  - recalculate_weights: rebuild routing_weights (now stamps staleness metadata)
"""

from __future__ import annotations

import logging
import math
import os
import random
import sqlite3

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


# ---------------------------------------------------------------------------
# cos_route_model
# ---------------------------------------------------------------------------


def route_model(
    conn: sqlite3.Connection,
    *,
    complexity: str,
    dimensions: int = 1,
    domain: str | None = None,
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

    # Query success rates per model for this complexity. Per-role attribution
    # (TASK-473 P4-9): credit the model that actually RAN the role
    # (formula_dispatches.model, keyed by task_marker), falling back to the
    # orchestrator model (task_outcomes.model) for tasks done with no role
    # dispatch. The DISTINCT subquery collapses multiple same-model dispatches in
    # one task to a single data point so one task isn't double-counted per role.
    rows = _model_success_rows(conn, complexity, domain)

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
        model_stats.append(
            {
                "model": d["model"],
                "success_rate": round(rate, 2),
                "sample_size": d["total"],
            }
        )
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
            f"{complexity}" + (f" {domain}" if domain else "") + f" tasks (n={best_total})"
        ),
        "fallback_model": fallback,
        "data_points": total,
        "model_stats": model_stats,
    }


def _model_success_rows(conn: sqlite3.Connection, complexity: str, domain: str | None) -> list:
    # Per-model (successes, total) for a complexity/domain bucket. Credits the
    # model that RAN the role (formula_dispatches.model by task_marker), falling
    # back to the orchestrator (task_outcomes.model); DISTINCT collapses repeat
    # same-model dispatches in one task. Shared by the frequentist + bandit paths.
    conditions = ["t.complexity = ?"]
    params: list = [complexity]
    if domain:
        conditions.append("t.domain = ?")
        params.append(domain)
    where = " AND ".join(conditions)
    return conn.execute(
        "SELECT model, "
        "SUM(CASE WHEN outcome = 'success' THEN 1 ELSE 0 END) AS successes, "
        "COUNT(*) AS total FROM ("
        "  SELECT DISTINCT t.task_id, COALESCE(fd.model, t.model) AS model, t.outcome "
        "  FROM task_outcomes t "
        "  LEFT JOIN formula_dispatches fd "
        "    ON fd.task_marker = t.task_id AND fd.model IS NOT NULL "
        f"  WHERE {where}"
        ") per_task_model "
        "WHERE model IS NOT NULL "
        "GROUP BY model "
        "HAVING total >= ?",
        [*params, MIN_SAMPLES_PER_BUCKET],
    ).fetchall()


def _sample_gamma(shape: float) -> float:
    # Marsaglia-Tsang: shape>=1 directly; boost shape<1 via the x**(1/shape) trick.
    if shape < 1.0:
        return _sample_gamma(shape + 1.0) * (random.random() ** (1.0 / shape))
    d = shape - 1.0 / 3.0
    c = 1.0 / math.sqrt(9.0 * d)
    while True:
        x = random.gauss(0.0, 1.0)
        v = (1.0 + c * x) ** 3
        if v <= 0:
            continue
        u = random.random()
        if u < 1.0 - 0.0331 * (x**4) or math.log(u) < 0.5 * x * x + d * (1.0 - v + math.log(v)):
            return d * v


def _sample_beta(a: float, b: float) -> float:
    x = _sample_gamma(a)
    y = _sample_gamma(b)
    return x / (x + y) if (x + y) > 0 else 0.5


def _model_cost_rank(model: str) -> float:
    m = (model or "").lower()
    if "opus" in m:
        return 1.0
    if "haiku" in m:
        return 0.0
    if "sonnet" in m:
        return 0.5
    return 0.5


def route_model_bandit(
    conn: sqlite3.Connection,
    *,
    complexity: str,
    dimensions: int = 1,
    domain: str | None = None,
) -> dict:
    """Thompson-sampling (Beta-Bernoulli) model router over the dispatch ledger; gated by COS_ROUTER_BANDIT.

    Flag unset OR cold-start (< COLD_START_THRESHOLD outcomes) OR no warm bucket
    delegates byte-for-byte to the frequentist route_model. Otherwise samples
    theta ~ Beta(1+successes, 1+failures) per model and picks the max, with an
    optional cost-tilt (COS_ROUTER_COST_TILT) nudging ties toward the cheaper tier.
    """
    if not os.environ.get("COS_ROUTER_BANDIT"):
        return route_model(conn, complexity=complexity, dimensions=dimensions, domain=domain)

    fallback = DEFAULT_MODELS.get(complexity, "sonnet")
    total = conn.execute("SELECT COUNT(*) FROM task_outcomes").fetchone()[0]
    if total < COLD_START_THRESHOLD:
        return route_model(conn, complexity=complexity, dimensions=dimensions, domain=domain)

    rows = _model_success_rows(conn, complexity, domain)
    if not rows:
        return route_model(conn, complexity=complexity, dimensions=dimensions, domain=domain)

    try:
        tilt = max(0.0, float(os.environ.get("COS_ROUTER_COST_TILT", "0") or "0"))
    except ValueError:
        tilt = 0.0

    best_model = fallback
    best_score = float("-inf")
    best_alpha = 1.0
    best_beta = 1.0
    model_stats = []
    for row in rows:
        d = dict(row)
        successes = int(d["successes"] or 0)
        n = int(d["total"] or 0)
        alpha = 1.0 + successes
        beta = 1.0 + max(0, n - successes)
        theta = _sample_beta(alpha, beta)
        score = theta - tilt * _model_cost_rank(d["model"])
        model_stats.append(
            {
                "model": d["model"],
                "alpha": alpha,
                "beta": beta,
                "sampled_theta": round(theta, 3),
                "sample_size": n,
            }
        )
        if score > best_score:
            best_score = score
            best_alpha = alpha
            best_beta = beta
            best_model = d["model"]

    # Confidence is the SELECTED model's posterior mean — deterministic for a given
    # history and always in [0,1] (the -inf seed guarantees a real selection even
    # under a large cost-tilt). The random Thompson draw drives only the arg-max
    # (exposed per-model as model_stats[*].sampled_theta).
    confidence = best_alpha / (best_alpha + best_beta)
    return {
        "recommended_model": best_model,
        "confidence": round(confidence, 2),
        "reason": (
            f"Thompson-sampled {best_model} (posterior mean {confidence:.3f}) over "
            f"{len(rows)} model(s) for {complexity}"
            + (f" {domain}" if domain else "")
            + (f", cost-tilt {tilt}" if tilt else "")
        ),
        "fallback_model": fallback,
        "data_points": total,
        "model_stats": model_stats,
        "method": "thompson",
    }


_CHEAPER_TIER = {"opus": "sonnet", "sonnet": "haiku", "haiku": "haiku"}
_REVIEW_ROLES = frozenset({"reviewer", "security_auditor", "observer"})


def reviewer_model(generator_model: str) -> str:
    # An independent reviewer needn't match the generator's tier — one rung
    # cheaper keeps a second opinion affordable. Returns the bare cheaper tier
    # (the adapter resolves the alias); matches by substring so a fully
    # qualified model id and its bare tier alias both downgrade. Empty in ->
    # empty out (caller default).
    m = (generator_model or "").lower()
    for tier, cheaper in _CHEAPER_TIER.items():
        if tier in m:
            return cheaper
    return generator_model


# ---------------------------------------------------------------------------
# cos_route_skill
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Router weight recalculation
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
    try:
        conn.execute(
            "UPDATE routing_weights SET last_recalc_at = CURRENT_TIMESTAMP, outcomes_at_recalc = ?",
            (total_outcomes,),
        )
    except sqlite3.OperationalError:
        pass  # migration v26 not yet applied — safe to skip

    conn.commit()
    return {"status": "ok", "weights_updated": count, "outcomes_stamped": total_outcomes}


# ---------------------------------------------------------------------------
# routing_drift — detect stale routing weights
# ---------------------------------------------------------------------------

_STALE_THRESHOLD = 15  # new outcomes since last recalc before drift is flagged


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


# ---------------------------------------------------------------------------
# failure_pattern_query — aggregate structured failure anatomy
# ---------------------------------------------------------------------------

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
