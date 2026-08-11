"""Transition Gate override audit (TASK-104)."""

from __future__ import annotations

from pydantic import BaseModel

from board_os._gates_result import ValidationMessage, ValidationResult, Verdict
from board_os.transition_gates import GatesConfig

# ────────────────────────────────────────────────────────────────────
# Override audit
# ────────────────────────────────────────────────────────────────────


class OverrideRequest(BaseModel):
    """Captured when COS_*_OVERRIDE=1 is set; rejected if reason is missing."""

    gate: str  # "dor" | "dod" | "wip" | "verify"
    reason: str
    actor: str  # COS_AGENT or fallback to "unknown"


def evaluate_override(
    gate: str,
    *,
    reason: str | None,
    actor: str | None,
    config: GatesConfig,
) -> tuple[ValidationResult, OverrideRequest | None]:
    """Validate an attempted gate override.

    Returns (result, request_or_None). When result.blocked, the override
    is rejected; callers must surface the message instead of bypassing
    the gate.
    """
    result = ValidationResult()
    pol = config.overrides
    if not pol.require_reason:
        return result, OverrideRequest(
            gate=gate,
            reason=reason or "",
            actor=actor or "unknown",
        )

    if not reason or not reason.strip():
        result.add(
            ValidationMessage(
                code="OVERRIDE_REASON_MISSING",
                severity=Verdict.BLOCK,
                message=(
                    f"Gate override on {gate!r} rejected: COS_OVERRIDE_REASON "
                    f"is required (>= {pol.min_reason_chars} chars). "
                    f'Example: COS_OVERRIDE_REASON="hotfix for INC-1234, '
                    f'verify will run in follow-up PR".'
                ),
            ),
        )
        return result, None

    if len(reason.strip()) < pol.min_reason_chars:
        result.add(
            ValidationMessage(
                code="OVERRIDE_REASON_TOO_SHORT",
                severity=Verdict.BLOCK,
                message=(
                    f"Override reason has {len(reason.strip())} chars; "
                    f"min is {pol.min_reason_chars}. Be specific so retro "
                    f"reviewers can audit the bypass."
                ),
            ),
        )
        return result, None

    return result, OverrideRequest(
        gate=gate,
        reason=reason.strip(),
        actor=actor or "unknown",
    )
