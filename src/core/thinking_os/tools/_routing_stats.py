"""Statistics the routers run on — data volume, per-model buckets, Beta sampling.

Separated from the routers themselves because the aggregation SQL and the
sampling maths change with how outcomes are measured, while the routers change
with what gets recommended. A leaf: it imports no sibling tool module.
"""

from __future__ import annotations

import logging
import math
import random
import sqlite3

logger = logging.getLogger("thinking_os.routing")

COLD_START_THRESHOLD = 10  # minimum outcomes before data-driven recommendations
MIN_SAMPLES_PER_BUCKET = 5  # minimum samples to recommend a specific model


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
