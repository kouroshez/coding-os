"""Coding OS — daily budget cap for sub-agent dispatch.

Reads env COS_DAILY_BUDGET_USD (float). If unset or <=0, gate disabled.
Computes today's accumulated cost from formula_dispatches.cost_usd
(date(created_at)=today UTC) and checks against the cap before allowing
a new dispatch.

Always fail-closed — when in doubt, return BudgetGate(allowed=True) so
a misconfigured DB never blocks legitimate work. Caller decides whether
to convert (allowed=False, reason) into a `fail()` envelope.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("coding_os.budget")

ENV_VAR = "COS_DAILY_BUDGET_USD"


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
    except Exception as exc:  # noqa: BLE001
        logger.debug("hub-settings budget read failed: %s", exc)
        return None


@dataclass
class BudgetGate:
    allowed: bool
    cap_usd: float | None
    spent_usd: float
    reason: str = ""


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
                "SELECT COALESCE(SUM(cost_usd), 0.0) "
                "FROM formula_dispatches "
                "WHERE date(created_at) = ?",
                (_today_utc_date(),),
            ).fetchone()
        except sqlite3.OperationalError as exc:
            logger.debug("budget query failed (schema?): %s", exc)
            return 0.0
        return float(row[0] or 0.0)
    finally:
        conn.close()


def check(db_path: str | Path, *, additional_estimate_usd: float = 0.0) -> BudgetGate:
    cap = _read_cap() or _read_hub_settings_cap()
    if cap is None:
        return BudgetGate(allowed=True, cap_usd=None, spent_usd=0.0)
    spent = _spent_today(db_path)
    projected = spent + max(0.0, float(additional_estimate_usd))
    if projected >= cap:
        reason = (
            f"daily budget exceeded: spent ${spent:.4f} "
            f"+ projected ${additional_estimate_usd:.4f} "
            f">= cap ${cap:.4f} (env {ENV_VAR}). "
            f"Reset at UTC midnight or unset {ENV_VAR}."
        )
        return BudgetGate(allowed=False, cap_usd=cap, spent_usd=spent, reason=reason)
    return BudgetGate(allowed=True, cap_usd=cap, spent_usd=spent)
