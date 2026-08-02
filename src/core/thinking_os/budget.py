"""Coding OS — daily budget cap for sub-agent dispatch.

Reads env COS_DAILY_BUDGET_USD (float). If unset or <=0, gate disabled.
Computes today's accumulated cost from formula_dispatches.cost_usd
(date(ts)=today UTC) and checks against the cap before allowing
a new dispatch.

Always fail-open — when in doubt, return BudgetGate(allowed=True) so
a misconfigured DB never blocks legitimate work. Caller decides whether
to convert (allowed=False, reason) into a `fail()` envelope.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import statistics
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("coding_os.budget")

ENV_VAR = "COS_DAILY_BUDGET_USD"
CHAIN_ENV_VAR = "COS_CHAIN_BUDGET_USD"


def _read_hub_settings_cap() -> float | None:
    """Fall back to .coding-os/hub-settings.json when env var is absent."""
    import json

    state_dir = os.environ.get("COS_STATE_DIR") or ".coding-os"
    path = Path(state_dir) / "hub-settings.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        bc = data.get("budget_cap", {})
        if not bc.get("enabled"):
            return None
        v = float(bc.get("cap_usd", 0))
        return v if v > 0 else None
    except Exception as exc:
        logger.debug("hub-settings budget read failed: %s", exc)
        return None


@dataclass
class BudgetGate:
    allowed: bool
    cap_usd: float | None
    spent_usd: float
    reason: str = ""
    level: str = "ok"  # utilization gauge: ok|info|warning|critical|hard_stop


def _today_utc_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _read_cap() -> float | None:
    raw = os.environ.get(ENV_VAR)
    if not raw:
        return None
    try:
        v = float(raw)
    except ValueError:
        logger.debug("invalid %s=%r - ignoring", ENV_VAR, raw)
        return None
    if v <= 0:
        return None
    return v


def _spent_today(db_path: str | Path) -> float:
    p = Path(db_path)
    if not p.exists():
        return 0.0
    try:
        conn = sqlite3.connect(str(p))
    except sqlite3.Error as exc:
        logger.debug("budget DB connect failed: %s", exc)
        return 0.0
    try:
        try:
            row = conn.execute(
                "SELECT COALESCE(SUM(cost_usd), 0.0) FROM formula_dispatches WHERE date(ts) = ?",
                (_today_utc_date(),),
            ).fetchone()
        except sqlite3.OperationalError as exc:
            logger.debug("budget query failed (schema?): %s", exc)
            return 0.0
        return float(row[0] or 0.0)
    finally:
        conn.close()


def _budget_utilization_level(spent: float, cap: float | None) -> str:
    # Gauge only — the fail-closed allow/deny stays in check(); this just labels
    # how close spend is to the cap so callers can warn before the hard stop.
    if not cap or cap <= 0:
        return "ok"
    pct = spent / cap
    if pct >= 1.0:
        return "hard_stop"
    if pct >= 0.9:
        return "critical"
    if pct >= 0.75:
        return "warning"
    if pct >= 0.5:
        return "info"
    return "ok"


def check(db_path: str | Path, *, additional_estimate_usd: float = 0.0) -> BudgetGate:
    cap = _read_cap() or _read_hub_settings_cap()
    if cap is None:
        return BudgetGate(allowed=True, cap_usd=None, spent_usd=0.0)
    spent = _spent_today(db_path)
    projected = spent + max(0.0, float(additional_estimate_usd))
    level = _budget_utilization_level(projected, cap)
    if projected >= cap:
        reason = (
            f"daily budget exceeded: spent ${spent:.4f} "
            f"+ projected ${additional_estimate_usd:.4f} "
            f">= cap ${cap:.4f} (env {ENV_VAR}). "
            f"Reset at UTC midnight or unset {ENV_VAR}."
        )
        return BudgetGate(allowed=False, cap_usd=cap, spent_usd=spent, reason=reason, level=level)
    return BudgetGate(allowed=True, cap_usd=cap, spent_usd=spent, level=level)


def _connect_ro(db_path: str | Path) -> sqlite3.Connection | None:
    p = Path(db_path)
    if not p.exists():
        return None
    try:
        return sqlite3.connect(str(p))
    except sqlite3.Error as exc:
        logger.debug("cost analytics DB connect failed: %s", exc)
        return None


ESTIMATE_WINDOW = 20


def estimate_dispatch_cost(db_path: str | Path, count: int) -> float:
    """Forward cost of `count` dispatches from the median recent dispatch; 0.0 without history."""
    if count <= 0:
        return 0.0
    conn = _connect_ro(db_path)
    if conn is None:
        return 0.0
    try:
        rows = conn.execute(
            "SELECT cost_usd FROM formula_dispatches "
            "WHERE cost_usd IS NOT NULL AND cost_usd > 0 "
            "ORDER BY id DESC LIMIT ?",
            (ESTIMATE_WINDOW,),
        ).fetchall()
    except sqlite3.OperationalError as exc:
        logger.debug("dispatch cost estimate query failed (schema?): %s", exc)
        return 0.0
    finally:
        conn.close()
    costs = [float(r[0]) for r in rows if r[0] is not None]
    if not costs:
        return 0.0
    return statistics.median(costs) * count


def cost_anomaly(db_path: str | Path, *, z_threshold: float = 3.5) -> dict:
    """Median+MAD modified-z anomaly over per-session formula_dispatches cost (n>=3 guard)."""
    conn = _connect_ro(db_path)
    if conn is None:
        return {"ok": True, "n": 0, "outliers": [], "reason": "no_db"}
    try:
        rows = conn.execute(
            "SELECT session_id, COALESCE(SUM(cost_usd), 0.0) AS c "
            "FROM formula_dispatches WHERE cost_usd IS NOT NULL "
            "GROUP BY session_id"
        ).fetchall()
    except sqlite3.OperationalError as exc:
        logger.debug("cost_anomaly query failed (schema?): %s", exc)
        return {"ok": True, "n": 0, "outliers": [], "reason": "schema"}
    finally:
        conn.close()
    costs = [(str(sid), float(c or 0.0)) for sid, c in rows if c]
    n = len(costs)
    if n < 3:
        return {"ok": True, "n": n, "outliers": [], "reason": "n<3"}
    values = [c for _, c in costs]
    med = statistics.median(values)
    deviations = [abs(v - med) for v in values]
    mad = statistics.median(deviations)
    if mad > 0:
        scale = mad / 0.6745
    else:
        # MAD=0 when >half the (cost-bearing) sessions share the median cost; fall
        # back to a mean-absolute-deviation modified-z so a lone spike still flags.
        mean_ad = sum(deviations) / len(deviations)
        if mean_ad <= 0:
            return {"ok": True, "n": n, "median": round(med, 6), "mad": 0.0, "outliers": []}
        scale = mean_ad * 1.253314
    outliers = []
    for sid, c in costs:
        z = (c - med) / scale
        if z > z_threshold:  # upper tail only — a cheap session is not a cost overrun
            outliers.append({"session_id": sid, "cost_usd": round(c, 6), "modified_z": round(z, 2)})
    outliers.sort(key=lambda o: abs(o["modified_z"]), reverse=True)
    return {
        "ok": not outliers,
        "n": n,
        "median": round(med, 6),
        "mad": round(mad, 6),
        "outliers": outliers,
    }


def cost_burn_rate(db_path: str | Path, *, window_days: int = 14) -> dict:
    """Latest-day vs prior-window-mean daily-spend delta + accelerating flag over formula_dispatches."""
    conn = _connect_ro(db_path)
    if conn is None:
        return {"days": 0, "reason": "no_db"}
    try:
        rows = conn.execute(
            "SELECT date(ts) AS day, COALESCE(SUM(cost_usd), 0.0) AS c "
            "FROM formula_dispatches WHERE cost_usd IS NOT NULL "
            "AND ts >= datetime('now', ?) GROUP BY day ORDER BY day",
            (f"-{int(window_days)} days",),
        ).fetchall()
    except sqlite3.OperationalError as exc:
        logger.debug("cost_burn_rate query failed (schema?): %s", exc)
        return {"days": 0, "reason": "schema"}
    finally:
        conn.close()
    daily = [(str(d), float(c or 0.0)) for d, c in rows]
    if len(daily) < 2:
        return {"days": len(daily), "reason": "insufficient"}
    latest_day, latest_cost = daily[-1]
    prior = [c for _, c in daily[:-1]]
    prior_mean = sum(prior) / len(prior) if prior else 0.0
    delta_pct = ((latest_cost - prior_mean) / prior_mean * 100.0) if prior_mean > 0 else None
    return {
        "days": len(daily),
        "latest_day": latest_day,
        "latest_cost_usd": round(latest_cost, 6),
        "prior_mean_usd": round(prior_mean, 6),
        "delta_pct": round(delta_pct, 1) if delta_pct is not None else None,
        "accelerating": bool(delta_pct is not None and delta_pct > 0),
        "partial_today": latest_day == _today_utc_date(),
    }


def _read_chain_cap() -> float | None:
    raw = os.environ.get(CHAIN_ENV_VAR)
    if not raw:
        return None
    try:
        v = float(raw)
    except ValueError:
        logger.debug("invalid %s=%r - ignoring", CHAIN_ENV_VAR, raw)
        return None
    return v if v > 0 else None


def _chain_spent(db_path: str | Path, task_marker: str) -> float:
    conn = _connect_ro(db_path)
    if conn is None:
        return 0.0
    try:
        try:
            row = conn.execute(
                "SELECT COALESCE(SUM(cost_usd), 0.0) FROM formula_dispatches WHERE task_marker = ?",
                (task_marker,),
            ).fetchone()
        except sqlite3.OperationalError as exc:
            logger.debug("chain budget query failed (schema?): %s", exc)
            return 0.0
        return float(row[0] or 0.0)
    finally:
        conn.close()


def chain_check(
    db_path: str | Path, task_marker: str, *, additional_estimate_usd: float = 0.0
) -> BudgetGate:
    """Per-chain (task_marker) USD ceiling over formula_dispatches; gate before another dispatch in the chain."""
    cap = _read_chain_cap()
    if cap is None or not task_marker:
        return BudgetGate(allowed=True, cap_usd=cap, spent_usd=0.0)
    spent = _chain_spent(db_path, task_marker)
    projected = spent + max(0.0, float(additional_estimate_usd))
    level = _budget_utilization_level(projected, cap)
    if projected >= cap:
        reason = (
            f"per-chain budget exceeded for {task_marker}: spent ${spent:.4f} "
            f"+ projected ${additional_estimate_usd:.4f} >= cap ${cap:.4f} (env {CHAIN_ENV_VAR})."
        )
        return BudgetGate(allowed=False, cap_usd=cap, spent_usd=spent, reason=reason, level=level)
    return BudgetGate(allowed=True, cap_usd=cap, spent_usd=spent, level=level)
