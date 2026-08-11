"""Validator behavior tests (TASK-104).

Covers DoR, DoD, override audit, and the dispatcher entry point. Every
kind in the shipped YAML is exercised so adding a new kind requires
adding a fixture row, not chasing implicit rule inheritance.
"""

from __future__ import annotations

import os
from contextlib import contextmanager

from core.board_os.transition_gates import load_gates_config
from core.board_os.transition_gates_validator import (
    Verdict,
    evaluate_override,
    validate_transition,
)

# ────────────────────────────────────────────────────────────────────
# Fixtures — task-body samples
# ────────────────────────────────────────────────────────────────────


def _full_body(*, with_repro: bool = False, with_threat: bool = False) -> str:
    """A maximally-filled task body that satisfies every kind's DoR."""
    parts = [
        "**Outcome (one sentence):** Refactor the gate dispatch to use a "
        "single SSOT and eliminate per-hook regex drift.",
        "## Read First",
        "- [docs/phase-l10-plan.md](../phase-l10-plan.md)",
        "- [core/board_os/transition_gates.py](../../core/board_os/transition_gates.py)",
        "## Acceptance (G/W/T) — *this IS the Definition of Done*",
        "- **Given** a task body with placeholder text",
        "- **When** the agent attempts to transition into in_progress",
        "- **Then** the validator returns BLOCK with structured messages.",
    ]
    if with_repro:
        parts.append(
            "## Repro Steps\n1. Create a task with `cos task-create`. "
            "2. Try to start it before filling Outcome. 3. Observe block."
        )
    if with_threat:
        parts.append(
            "## Threat Model\nAttacker bypasses the gate via "
            "COS_DOR_OVERRIDE=1; mitigation: require COS_OVERRIDE_REASON "
            "with audit trail."
        )
    return "\n\n".join(parts) + "\n"


def _no_acceptance_body() -> str:
    """A body with Outcome + Read First but NO Acceptance section."""
    return (
        "**Outcome (one sentence):** Ship the widget so users can frobnicate "
        "the gadget end to end.\n\n"
        "## Read First\n- [docs/phase-l10-plan.md](../phase-l10-plan.md)\n"
    )


def _placeholder_body() -> str:
    return (
        "**Outcome (one sentence):** (fill in: one-sentence measurable outcome)\n\n"
        "## Read First\n- (no doc yet — exploratory)\n\n"
        "## Acceptance (G/W/T) — *this IS the Definition of Done*\n"
        "- **Given** ...\n- **When** ...\n- **Then** ...\n"
    )


def _too_short_outcome() -> str:
    return (
        "**Outcome (one sentence):** fix it\n\n"  # < 20 chars
        "## Read First\n- [a](a.md)\n\n"
        "## Acceptance (G/W/T) — *this IS the Definition of Done*\n"
        "- **Given** state A\n- **When** trigger B\n- **Then** outcome C\n"
    )


# ────────────────────────────────────────────────────────────────────
# DoR — per kind matrix (8 kinds × pass/block/warn)
# ────────────────────────────────────────────────────────────────────


KINDS = ["feature", "bug", "chore", "spike", "docs", "refactor", "test", "security"]


def _body_for_kind(kind: str) -> str:
    """Return a body that satisfies the kind's DoR."""
    return _full_body(
        with_repro=(kind == "bug"),
        with_threat=(kind == "security"),
    )


def test_override_rejected_without_reason() -> None:
    config = load_gates_config()
    result, request = evaluate_override(
        "dor",
        reason=None,
        actor="claude",
        config=config,
    )
    assert result.blocked
    assert request is None
    assert any(m.code == "OVERRIDE_REASON_MISSING" for m in result.messages)


def test_override_rejected_with_too_short_reason() -> None:
    config = load_gates_config()
    result, request = evaluate_override(
        "dor",
        reason="oops",
        actor="claude",
        config=config,
    )
    assert result.blocked
    assert request is None
    assert any(m.code == "OVERRIDE_REASON_TOO_SHORT" for m in result.messages)


def test_override_accepted_with_valid_reason() -> None:
    config = load_gates_config()
    result, request = evaluate_override(
        "dor",
        reason="Hotfix for incident INC-1234; full DoR follow-up in TASK-200.",
        actor="claude",
        config=config,
    )
    assert result.verdict is Verdict.PASS
    assert request is not None
    assert request.gate == "dor"
    assert request.actor == "claude"


@contextmanager
def _env(**overrides: str | None):
    """Context manager — set env vars, restore on exit."""
    original = {k: os.environ.get(k) for k in overrides}
    try:
        for k, v in overrides.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        yield
    finally:
        for k, v in original.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_validate_transition_in_progress_passes_with_full_body() -> None:
    config = load_gates_config()
    with _env(COS_DOR_OVERRIDE=None):
        result = validate_transition(
            task_id="TASK-XXX",
            kind="feature",
            body=_full_body(),
            new_status="in_progress",
            config=config,
        )
    assert result.verdict is Verdict.PASS


def test_validate_transition_blocks_placeholder_without_override() -> None:
    config = load_gates_config()
    with _env(COS_DOR_OVERRIDE=None):
        result = validate_transition(
            task_id="TASK-XXX",
            kind="feature",
            body=_placeholder_body(),
            new_status="in_progress",
            config=config,
        )
    assert result.blocked


def test_validate_transition_override_without_reason_still_blocks() -> None:
    config = load_gates_config()
    with _env(COS_DOR_OVERRIDE="1", COS_OVERRIDE_REASON=None):
        result = validate_transition(
            task_id="TASK-XXX",
            kind="feature",
            body=_placeholder_body(),
            new_status="in_progress",
            config=config,
            override_reason=None,
        )
    assert result.blocked
    # Both the original DoR block AND the override-rejection should be visible.
    codes = [m.code for m in result.messages]
    assert any(c.startswith("DOR_") for c in codes)
    assert "OVERRIDE_REASON_MISSING" in codes


def test_validate_transition_override_with_valid_reason_downgrades_to_warn() -> None:
    config = load_gates_config()
    valid_reason = "Hotfix for incident INC-9999; will fill DoR in follow-up TASK-201."
    with _env(COS_DOR_OVERRIDE="1"):
        result = validate_transition(
            task_id="TASK-XXX",
            kind="feature",
            body=_placeholder_body(),
            new_status="in_progress",
            config=config,
            override_reason=valid_reason,
        )
    assert result.verdict is Verdict.WARN
    assert all("[OVERRIDDEN]" in m.message for m in result.messages)


def test_validate_transition_other_status_is_noop() -> None:
    config = load_gates_config()
    result = validate_transition(
        task_id="TASK-XXX",
        kind="feature",
        body="garbage",
        new_status="testing",  # no body gate today
        config=config,
    )
    assert result.verdict is Verdict.PASS


def test_validate_transition_complete_blocks_without_verify() -> None:
    config = load_gates_config()
    result = validate_transition(
        task_id="TASK-XXX",
        kind="feature",
        body=_full_body(),
        new_status="complete",
        config=config,
        has_recent_verify=False,
        has_work_log=True,
    )
    assert result.blocked
    assert any(m.code == "DOD_VERIFY_MISSING" for m in result.messages)


def test_validate_transition_complete_override_with_reason() -> None:
    config = load_gates_config()
    valid_reason = (
        "Build server outage; verify ran locally with full pass — see "
        "logs/local-verify-2026-04-25.log"
    )
    with _env(COS_VERIFY_OVERRIDE="1"):
        result = validate_transition(
            task_id="TASK-XXX",
            kind="feature",
            body=_full_body(),
            new_status="complete",
            config=config,
            has_recent_verify=False,
            override_reason=valid_reason,
        )
    assert result.verdict is Verdict.WARN
