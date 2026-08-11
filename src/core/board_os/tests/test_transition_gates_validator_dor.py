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


def test_read_first_missing_paths_flags_only_dead_repo_paths(tmp_path) -> None:
    # Regression guard for the Read First dead-link check (C5a): only repo paths
    # that don't resolve are flagged; URLs, globs, prose and real files are not.
    from core.board_os.transition_gates_validator import _read_first_missing_paths

    (tmp_path / "src" / "core").mkdir(parents=True)
    (tmp_path / "src" / "core" / "real.py").write_text("x", encoding="utf-8")

    text = (
        "- src/core/real.py — exists\n"
        "- src/core/missing.py — gone\n"
        "- [doc](docs/none.md) — dead link\n"
        "- https://example.com — external, ignored\n"
        "- src/core/*.py — glob, ignored\n"
        "- just prose, no path\n"
    )
    missing = _read_first_missing_paths(text, str(tmp_path))

    assert "src/core/missing.py" in missing
    assert "docs/none.md" in missing
    assert "src/core/real.py" not in missing
    assert not any("example.com" in m for m in missing)
    assert not any("*" in m for m in missing)


def test_dead_link_check_is_skipped_without_project_root() -> None:
    # Pure-validator path: no project_root means no filesystem touch, so a body
    # with dead Read First links still evaluates without a dead-link warning.
    config = load_gates_config()
    body = (
        "**Outcome (one sentence):** A real outcome sentence that is long enough.\n"
        "## Read First\n- src/core/totally/made/up.py — nope\n"
        "## Acceptance (G/W/T)\n- **Given** a, **When** b, **Then** c\n"
    )
    result = evaluate_dor("feature", body, config)  # no project_root
    assert not any(m.code == "DOR_READ_FIRST_DEAD_LINK" for m in result.messages)
