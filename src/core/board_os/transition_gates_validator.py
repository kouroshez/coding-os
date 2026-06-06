"""Transition Gate validator (TASK-104)."""

from __future__ import annotations

import os
import re
from enum import Enum

from pydantic import BaseModel, Field

from board_os.parser import _extract_body_sections, _extract_outcome
from board_os.transition_gates import (
    DoDKindRules,
    DoRKindRules,
    GatesConfig,
    SectionRule,
)

# ────────────────────────────────────────────────────────────────────
# Result types
# ────────────────────────────────────────────────────────────────────


class Verdict(str, Enum):
    PASS = "pass"
    WARN = "warn"
    BLOCK = "block"


class ValidationMessage(BaseModel):
    code: str  # stable identifier (e.g. "DOR_OUTCOME_MISSING")
    severity: Verdict
    field: str | None = None
    message: str  # human-readable repair hint


class ValidationResult(BaseModel):
    verdict: Verdict = Verdict.PASS
    messages: list[ValidationMessage] = Field(default_factory=list)

    @property
    def blocked(self) -> bool:
        return self.verdict is Verdict.BLOCK

    def add(self, msg: ValidationMessage) -> None:
        self.messages.append(msg)
        # Verdict escalates: PASS → WARN → BLOCK; never demotes.
        if msg.severity is Verdict.BLOCK:
            self.verdict = Verdict.BLOCK
        elif msg.severity is Verdict.WARN and self.verdict is Verdict.PASS:
            self.verdict = Verdict.WARN


# ────────────────────────────────────────────────────────────────────
# Section evaluation
# ────────────────────────────────────────────────────────────────────


def _section_text_or_none(body: str, name: str) -> str | None:
    """Pull a section's body text. Outcome is special-cased (lives outside H2s).

    H2 headers in real task files often carry trailing decoration like
    "## Acceptance (G/W/T) — *this IS the Definition of Done*". Match by
    prefix so a rule named "Acceptance" still resolves to that header.
    """
    if name == "Outcome":
        return _extract_outcome(body)
    sections = _extract_body_sections(body)
    if name in sections:
        return sections[name]
    target = name.lower()
    for header, text in sections.items():
        # Prefix match — header must start with the configured name as a
        # whole word, not as a substring of a different word.
        norm = header.lower()
        if (
            norm == target
            or norm.startswith(target + " ")
            or norm.startswith(
                target + "(",
            )
        ):
            return text
    return None


def _count_list_items(text: str) -> int:
    """Count `- ` bullets in a section, ignoring empty lines."""
    return sum(1 for line in text.splitlines() if line.lstrip().startswith("- "))


def _evaluate_section(
    name: str,
    rule: SectionRule,
    body: str,
    result: ValidationResult,
) -> None:
    """Apply one SectionRule and append messages on violation."""
    text = _section_text_or_none(body, name)

    if rule.required and (text is None or not text.strip()):
        result.add(
            ValidationMessage(
                code=f"DOR_{_slug(name)}_MISSING",
                severity=Verdict.BLOCK,
                field=name,
                message=(
                    f'Section "{name}" is required but missing or empty. '
                    f"Fill it in the task body before transitioning."
                ),
            ),
        )
        return  # downstream checks need text content

    if text is None:
        return  # not required and absent — fine

    stripped = text.strip()

    if rule.min_chars and len(stripped) < rule.min_chars:
        result.add(
            ValidationMessage(
                code=f"DOR_{_slug(name)}_TOO_SHORT",
                severity=Verdict.BLOCK,
                field=name,
                message=(
                    f'Section "{name}" has {len(stripped)} chars; needs '
                    f"at least {rule.min_chars}. Be more specific."
                ),
            ),
        )

    for sub in rule.forbid_substrings:
        if sub in stripped:
            result.add(
                ValidationMessage(
                    code=f"DOR_{_slug(name)}_PLACEHOLDER",
                    severity=Verdict.BLOCK,
                    field=name,
                    message=(
                        f'Section "{name}" still contains placeholder '
                        f'text "{sub}". Replace with real content.'
                    ),
                ),
            )

    for pat in rule.forbid_regex:
        try:
            if re.search(pat, stripped):
                result.add(
                    ValidationMessage(
                        code=f"DOR_{_slug(name)}_PLACEHOLDER",
                        severity=Verdict.BLOCK,
                        field=name,
                        message=(
                            f'Section "{name}" matches forbidden pattern '
                            f"/{pat}/. Replace with real content."
                        ),
                    ),
                )
        except re.error:
            # Bad regex in config — fail loud at validate-time but surface
            # as PASS so a config typo doesn't block real work.
            continue

    for sub in rule.required_subitems:
        if sub not in stripped:
            result.add(
                ValidationMessage(
                    code=f"DOR_{_slug(name)}_SUBITEM_MISSING",
                    severity=Verdict.BLOCK,
                    field=name,
                    message=(
                        f'Section "{name}" must include "{sub}". '
                        f"Acceptance follows the G/W/T template."
                    ),
                ),
            )

    if rule.min_items:
        items = _count_list_items(stripped)
        if items < rule.min_items:
            result.add(
                ValidationMessage(
                    code=f"DOR_{_slug(name)}_TOO_FEW_ITEMS",
                    severity=Verdict.BLOCK,
                    field=name,
                    message=(
                        f'Section "{name}" has {items} bullet(s); needs at least {rule.min_items}.'
                    ),
                ),
            )


def _slug(name: str) -> str:
    """Section name → uppercase ASCII tag for error codes."""
    return re.sub(r"[^A-Z0-9]+", "_", name.upper()).strip("_")


# ────────────────────────────────────────────────────────────────────
# DoR / DoD entry points
# ────────────────────────────────────────────────────────────────────


def evaluate_dor(
    kind: str,
    body: str,
    config: GatesConfig,
) -> ValidationResult:
    """Check a task body against Definition-of-Ready for its kind."""
    result = ValidationResult()
    rules: DoRKindRules = config.definition_of_ready.for_kind(kind)
    for name, rule in rules.sections.items():
        if rule is None:
            continue
        _evaluate_section(name, rule, body, result)
    return result


def evaluate_dod(
    kind: str,
    *,
    has_recent_verify: bool,
    verify_age_seconds: int | None,
    has_work_log: bool,
    config: GatesConfig,
) -> ValidationResult:
    """Check Definition-of-Done state for a kind.

    The validator does not read the verify file or DB itself — it accepts
    booleans/ages from the caller. This keeps the validator pure and
    testable without filesystem fixtures.
    """
    result = ValidationResult()
    rules: DoDKindRules = config.definition_of_done.for_kind(kind)

    if rules.require_verify:
        if not has_recent_verify:
            result.add(
                ValidationMessage(
                    code="DOD_VERIFY_MISSING",
                    severity=Verdict.BLOCK,
                    message=(
                        f"Definition of Done: kind={kind!r} requires a "
                        f"recent verify run. None recorded. Run `make verify` "
                        f"(or the matrix command) before task-done."
                    ),
                ),
            )
        elif verify_age_seconds is not None and verify_age_seconds > rules.verify_max_age_seconds:
            result.add(
                ValidationMessage(
                    code="DOD_VERIFY_STALE",
                    severity=Verdict.BLOCK,
                    message=(
                        f"Verify is {verify_age_seconds}s old; max allowed "
                        f"is {rules.verify_max_age_seconds}s. Re-run verify."
                    ),
                ),
            )

    if rules.require_work_log and not has_work_log:
        result.add(
            ValidationMessage(
                code="DOD_WORK_LOG_MISSING",
                severity=Verdict.WARN,
                message=(
                    f"Definition of Done: kind={kind!r} expects at least "
                    f"one Work Log entry. Append a one-liner before "
                    f"task-done."
                ),
            ),
        )
    return result


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


# ────────────────────────────────────────────────────────────────────
# High-level entry point — used by hook + workflow alike
# ────────────────────────────────────────────────────────────────────


def validate_transition(
    *,
    task_id: str,
    kind: str,
    body: str,
    new_status: str,
    config: GatesConfig,
    has_recent_verify: bool = False,
    verify_age_seconds: int | None = None,
    has_work_log: bool = False,
    override_reason: str | None = None,
    override_actor: str | None = None,
) -> ValidationResult:
    """Single dispatch: route to the right evaluator based on `new_status`.

    Override semantics: if `COS_DOR_OVERRIDE=1` (or DoD/WIP/verify equivalents)
    is set in the environment, AND `override_reason` is provided and meets
    policy, the gate's BLOCK messages are downgraded to WARN. Otherwise the
    override request is rejected and the original BLOCK stands.

    `task_id` is unused today but accepted so future audit emission can
    correlate with the DB row without an extra parameter.
    """
    del task_id  # reserved for audit emission — see

    if new_status == "in_progress":
        result = evaluate_dor(kind, body, config)
        gate_name = "dor"
        env_flag = "COS_DOR_OVERRIDE"
    elif new_status == "complete":
        result = evaluate_dod(
            kind,
            has_recent_verify=has_recent_verify,
            verify_age_seconds=verify_age_seconds,
            has_work_log=has_work_log,
            config=config,
        )
        gate_name = "dod"
        env_flag = "COS_VERIFY_OVERRIDE"
    else:
        # Other transitions (testing, blocked, icebox, emergency) have no
        # body-based gate today.  WIP cap is checked elsewhere.
        return result_pass()

    if not result.blocked:
        return result

    if os.environ.get(env_flag) != "1":
        return result

    override_result, _ = evaluate_override(
        gate_name,
        reason=override_reason,
        actor=override_actor,
        config=config,
    )
    if override_result.blocked:
        # Override request itself was rejected — keep the gate blocking
        # AND surface the override-rejection reason.
        for msg in override_result.messages:
            result.add(msg)
        return result

    # Valid override — downgrade BLOCK messages to WARN so the audit row
    # captures what was bypassed.
    downgraded = ValidationResult()
    for m in result.messages:
        downgraded.add(
            ValidationMessage(
                code=m.code,
                severity=Verdict.WARN if m.severity is Verdict.BLOCK else m.severity,
                field=m.field,
                message=f"[OVERRIDDEN] {m.message}",
            ),
        )
    return downgraded


def result_pass() -> ValidationResult:
    return ValidationResult()


__all__ = [
    "OverrideRequest",
    "ValidationMessage",
    "ValidationResult",
    "Verdict",
    "evaluate_dod",
    "evaluate_dor",
    "evaluate_override",
    "result_pass",
    "validate_transition",
]
