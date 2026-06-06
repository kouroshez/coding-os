"""Validator behavior tests (TASK-104).

Covers DoR, DoD, override audit, and the dispatcher entry point. Every
kind in the shipped YAML is exercised so adding a new kind requires
adding a fixture row, not chasing implicit rule inheritance.
"""

from __future__ import annotations

import os
from contextlib import contextmanager

import pytest

from core.board_os.transition_gates import load_gates_config
from core.board_os.transition_gates_validator import (
    Verdict,
    evaluate_dod,
    evaluate_dor,
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


@pytest.mark.parametrize("kind", KINDS)
def test_dor_pass_for_each_kind(kind: str) -> None:
    config = load_gates_config()
    body = _body_for_kind(kind)
    result = evaluate_dor(kind, body, config)
    assert result.verdict is Verdict.PASS, (
        f"kind={kind} body should pass DoR; got messages: "
        f"{[(m.code, m.message) for m in result.messages]}"
    )


@pytest.mark.parametrize("kind", KINDS)
def test_dor_block_on_placeholder_body(kind: str) -> None:
    config = load_gates_config()
    result = evaluate_dor(kind, _placeholder_body(), config)
    assert result.blocked, f"kind={kind} placeholder body must BLOCK"
    # At least one DOR_*_PLACEHOLDER or _MISSING code should be present.
    codes = [m.code for m in result.messages]
    assert any(c.endswith("_PLACEHOLDER") or c.endswith("_MISSING") for c in codes), (
        f"kind={kind} expected placeholder/missing code; got {codes}"
    )


@pytest.mark.parametrize("kind", KINDS)
def test_dor_block_on_short_outcome(kind: str) -> None:
    config = load_gates_config()
    result = evaluate_dor(kind, _too_short_outcome(), config)
    assert result.blocked, f"kind={kind} short outcome must BLOCK"
    assert any("OUTCOME" in m.code for m in result.messages)


def test_dor_chore_does_not_require_acceptance() -> None:
    """Chore kind is relaxed — Outcome only."""
    config = load_gates_config()
    body = "**Outcome (one sentence):** Bump dependency X to v2.3.4 for the audit notice.\n"
    result = evaluate_dor("chore", body, config)
    assert result.verdict is Verdict.PASS, [(m.code, m.message) for m in result.messages]


def test_dor_spike_does_not_require_read_first() -> None:
    config = load_gates_config()
    body = (
        "**Outcome (one sentence):** Investigate whether kuzu can replace "
        "sqlite for the graph layer.\n"
    )
    result = evaluate_dor("spike", body, config)
    assert result.verdict is Verdict.PASS


def test_dor_bug_requires_repro_steps() -> None:
    config = load_gates_config()
    body = _full_body(with_repro=False)  # no Repro Steps section
    result = evaluate_dor("bug", body, config)
    assert result.blocked
    assert any(m.code == "DOR_REPRO_STEPS_MISSING" for m in result.messages)


def test_dor_security_requires_threat_model() -> None:
    config = load_gates_config()
    body = _full_body(with_threat=False)  # no Threat Model section
    result = evaluate_dor("security", body, config)
    assert result.blocked
    assert any(m.code == "DOR_THREAT_MODEL_MISSING" for m in result.messages)


# ────────────────────────────────────────────────────────────────────
# DoD — per kind matrix
# ────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("kind", KINDS)
def test_dod_pass_when_all_satisfied(kind: str) -> None:
    config = load_gates_config()
    result = evaluate_dod(
        kind,
        has_recent_verify=True,
        verify_age_seconds=60,
        has_work_log=True,
        config=config,
    )
    assert result.verdict is Verdict.PASS


def test_dod_blocks_when_verify_missing_for_default_kinds() -> None:
    config = load_gates_config()
    for kind in ("feature", "bug", "refactor", "test", "security", "spike", "chore"):
        result = evaluate_dod(
            kind,
            has_recent_verify=False,
            verify_age_seconds=None,
            has_work_log=True,
            config=config,
        )
        assert result.blocked, f"kind={kind} without verify must BLOCK"
        assert any(m.code == "DOD_VERIFY_MISSING" for m in result.messages)


def test_dod_docs_kind_skips_verify() -> None:
    """Docs tasks don't require verify."""
    config = load_gates_config()
    result = evaluate_dod(
        "docs",
        has_recent_verify=False,
        verify_age_seconds=None,
        has_work_log=True,
        config=config,
    )
    assert result.verdict is Verdict.PASS


def test_dod_blocks_on_stale_verify() -> None:
    config = load_gates_config()
    result = evaluate_dod(
        "feature",
        has_recent_verify=True,
        verify_age_seconds=10_000,  # > 1800s default
        has_work_log=True,
        config=config,
    )
    assert result.blocked
    assert any(m.code == "DOD_VERIFY_STALE" for m in result.messages)


def test_dod_warns_on_missing_work_log() -> None:
    config = load_gates_config()
    result = evaluate_dod(
        "feature",
        has_recent_verify=True,
        verify_age_seconds=60,
        has_work_log=False,
        config=config,
    )
    # work_log missing is WARN, not BLOCK
    assert result.verdict is Verdict.WARN
    assert any(m.code == "DOD_WORK_LOG_MISSING" for m in result.messages)


def test_dod_chore_skips_work_log_warning() -> None:
    config = load_gates_config()
    result = evaluate_dod(
        "chore",
        has_recent_verify=True,
        verify_age_seconds=60,
        has_work_log=False,
        config=config,
    )
    assert result.verdict is Verdict.PASS


# ────────────────────────────────────────────────────────────────────
# Override audit — accept / reject / silent-bypass-prevention
# ────────────────────────────────────────────────────────────────────


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


# ────────────────────────────────────────────────────────────────────
# Dispatcher (validate_transition) — integration of override + result
# ────────────────────────────────────────────────────────────────────


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


# ────────────────────────────────────────────────────────────────────
# Stable error codes — ensure UI/clients can rely on them
# ────────────────────────────────────────────────────────────────────


def test_error_codes_use_stable_prefix() -> None:
    config = load_gates_config()
    result = evaluate_dor("feature", _placeholder_body(), config)
    for m in result.messages:
        assert m.code.startswith("DOR_"), f"code {m.code!r} missing DOR_ prefix"
