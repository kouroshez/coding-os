"""
Thinking OS — MCP routing tools (TASK-145).

Tools for data-driven model and skill selection, failure pattern analysis,
and autonomous routing evolution:
  - cos_route_model: complexity → model recommendation
  - cos_route_skill: task context → skill recommendation
  - failure_pattern_query: aggregate structured failure anatomy
  - routing_drift: detect stale routing weights vs. current outcome patterns
  - recalculate_weights: rebuild routing_weights (now stamps staleness metadata)

The model router lives here; skill routing, weight recalculation, failure
anatomy, and the shared statistics moved to leaf siblings and are re-exported
below, so every `from tools.routing import …` keeps resolving. The two model
routers stay in one module because the bandit delegates to the frequentist —
callers (and tests) patch `routing.route_model` and expect both to follow.
"""

from __future__ import annotations

import logging
import os
import sqlite3

from ._routing_failures import (
    _VALID_ROOT_CAUSES as _VALID_ROOT_CAUSES,
    failure_pattern_query as failure_pattern_query,
)
from ._routing_skill import (
    DEFAULT_SKILLS as DEFAULT_SKILLS,
    route_skill as route_skill,
)
from ._routing_stats import (
    COLD_START_THRESHOLD,
    MIN_SAMPLES_PER_BUCKET as MIN_SAMPLES_PER_BUCKET,
    _data_confidence,
    _model_cost_rank,
    _model_success_rows,
    _sample_beta,
    _sample_gamma as _sample_gamma,
)
from ._routing_weights import (
    _STALE_THRESHOLD as _STALE_THRESHOLD,
    WEIGHT_STORE_THRESHOLD as WEIGHT_STORE_THRESHOLD,
    WEIGHT_USE_THRESHOLD as WEIGHT_USE_THRESHOLD,
    recalculate_weights as recalculate_weights,
    routing_drift as routing_drift,
)

logger = logging.getLogger("thinking_os.routing")

# Static defaults from performance.md and skill-enforcement.md
DEFAULT_MODELS = {
    "CLEAR": "sonnet",
    "COMPLICATED": "sonnet",
    "COMPLEX": "opus",
    "CHAOTIC": "sonnet",
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
    # ( P4-9): credit the model that actually RAN the role
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
