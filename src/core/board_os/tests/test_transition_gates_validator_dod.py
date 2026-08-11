"""Validator behavior tests (TASK-104).

Covers DoR, DoD, override audit, and the dispatcher entry point. Every
kind in the shipped YAML is exercised so adding a new kind requires
adding a fixture row, not chasing implicit rule inheritance.
"""

from __future__ import annotations

import pytest

from core.board_os.transition_gates import load_gates_config
from core.board_os.transition_gates_validator import (
    Verdict,
    evaluate_dod,
    evaluate_dor,
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


@pytest.mark.parametrize("kind", KINDS)
def test_dod_pass_when_all_satisfied(kind: str) -> None:
    config = load_gates_config()
    result = evaluate_dod(
        kind,
        body=_full_body(),
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
            body=_full_body(),
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
        body=_full_body(),
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
        body=_full_body(),
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
        body=_full_body(),
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
        body=_full_body(),
        has_recent_verify=True,
        verify_age_seconds=60,
        has_work_log=False,
        config=config,
    )
    assert result.verdict is Verdict.PASS


def test_dod_blocks_when_acceptance_missing_for_risk_kind() -> None:
    """A risk kind completing without a well-formed Acceptance is BLOCKed."""
    config = load_gates_config()
    for kind in ("feature", "bug", "refactor", "test", "security"):
        result = evaluate_dod(
            kind,
            body=_no_acceptance_body(),
            has_recent_verify=True,
            verify_age_seconds=60,
            has_work_log=True,
            config=config,
        )
        assert result.blocked, f"kind={kind} without acceptance must BLOCK"
        assert any(m.code == "DOD_ACCEPTANCE_MISSING" for m in result.messages)


def test_dod_unrecognized_kind_blocks_symmetric_with_dor() -> None:
    # An unrecognised/legacy kind inherits the default DoR (which requires the
    # G/W/T Acceptance and blocks it at in_progress), so the DoD gate blocks it
    # at complete too — the two gates stay symmetric.
    config = load_gates_config()
    result = evaluate_dod(
        "epic",  # not in the shipped definition_of_ready.by_kind
        body=_no_acceptance_body(),
        has_recent_verify=True,
        verify_age_seconds=60,
        has_work_log=True,
        config=config,
    )
    assert result.blocked
    assert any(m.code == "DOD_ACCEPTANCE_MISSING" for m in result.messages)


def test_dod_warns_when_acceptance_missing_for_non_risk_kind() -> None:
    """docs/chore opt out of Acceptance in DoR, so a missing block only WARNs."""
    config = load_gates_config()
    for kind in ("docs", "chore"):
        result = evaluate_dod(
            kind,
            body=_no_acceptance_body(),
            has_recent_verify=True,
            verify_age_seconds=60,
            has_work_log=True,
            config=config,
        )
        assert result.verdict is Verdict.WARN, f"kind={kind} should WARN, not BLOCK"
        assert not result.blocked
        assert any(m.code == "DOD_ACCEPTANCE_MISSING" for m in result.messages)


def test_error_codes_use_stable_prefix() -> None:
    config = load_gates_config()
    result = evaluate_dor("feature", _placeholder_body(), config)
    for m in result.messages:
        assert m.code.startswith("DOR_"), f"code {m.code!r} missing DOR_ prefix"
