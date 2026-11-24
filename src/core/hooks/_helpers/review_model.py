"""Which model reviews a testing round: the task's weight, the policy, and the session's model.

Contract: docs/engineering/agent-supervision.md § When dispatch fires by itself.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

WEIGHTY_GATES = ("COMPLEX", "CHAOTIC")
WEIGHTY_TIMEOUT_S = 420.0
# The session's effort cannot be read from a hook; a weighty review on the
# session's model runs at "high" instead of the adapter's automatic xhigh.
WEIGHTY_SESSION_EFFORT = "high"

_GATE_LEVELS = ("CLEAR", "COMPLICATED", "COMPLEX", "CHAOTIC", "CONFUSION")
# Claude families by strength. A model whose strength is unknown (another
# provider's) never stands in for the role's own tier.
_TIER_RANK = {"haiku": 1, "sonnet": 2, "opus": 3, "fable": 3}
REVIEW_FLOOR_RANK = _TIER_RANK["sonnet"]


def model_tier(model: str) -> str:
    lowered = model.lower()
    return next((tier for tier in _TIER_RANK if tier in lowered), "")


def review_weight(panel_dir: Path, security: bool) -> str:
    # The gate the agent recorded: "<session> <LEVEL> <dims> [why]"; only the level
    # token counts. A security-sensitive diff is weighty whatever the gate says.
    try:
        recorded = (panel_dir / ".thinking_os-gate").read_text(encoding="utf-8").split()
    except OSError:
        recorded = []
    level = next((token.upper() for token in recorded if token.upper() in _GATE_LEVELS), "")
    return "COMPLEX" if security or level in WEIGHTY_GATES else "COMPLICATED"


def routed(policy: dict[str, Any], complexity: str) -> bool:
    # The same test the dispatcher applies, so a pin below the adaptive gate is ignored here too.
    try:
        from thinking_os import supervision

        return bool(supervision.policy_applies(policy, complexity))
    except Exception as exc:
        logger.debug("supervision policy unreadable, treating routing as off: %s", exc)
        return False


def session_review_model(session_adapter: str, session_model: str) -> str:
    # The operator's model reviews a weighty change only if the adapter lists it
    # and it is known to be no weaker than a review's default tier (Sonnet).
    try:
        from thinking_os.adapter_registry import load_adapter_records

        record = load_adapter_records().get(session_adapter)
    except Exception as exc:
        logger.debug("adapter catalog unreadable for %s: %s", session_adapter, exc)
        return ""
    catalog = {
        str(model.get("id")) for model in (record.models if record else []) if model.get("id")
    }
    if session_model not in catalog:
        return ""
    rank = _TIER_RANK.get(model_tier(session_model), 0)
    return session_model if rank >= REVIEW_FLOOR_RANK else ""


def weighted(
    targets: list[dict[str, Any]], complexity: str, session_adapter: str, session_model: str
) -> list[dict[str, Any]]:
    # A weighty unpinned review runs on the model the operator chose for the
    # session; a routine one keeps the role default. A pin always wins.
    weighed: list[dict[str, Any]] = []
    for target in targets:
        target = {**target, "complexity": complexity}
        on_session = not target.get("pinned") and target["adapter"] == session_adapter
        if complexity == "COMPLEX" and on_session and session_model:
            target["model"] = session_model
            target["effort"] = WEIGHTY_SESSION_EFFORT
        weighed.append(target)
    return weighed
