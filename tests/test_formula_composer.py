"""
Phase N — Formula Composer tests.

Validate the 4-tier strategy:
  1. Situation override (highest priority)
  2. Preset match (scored)
  3. Composer fallback (per-role scoring)
  4. Hard fallback (never empty)

Plus: preset version stamping (N.5-C), effective_threshold stamping,
canonical researcher→refactorer ordering, parallel dispatch metadata.

Spec: docs/phase-n-role-based-routing-plan.md §2.3 · §7a
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_THINKING_OS = Path(__file__).resolve().parent.parent / "src" / "core" / "thinking_os"
if str(_THINKING_OS) not in sys.path:
    sys.path.insert(0, str(_THINKING_OS))

from cognition_schemas import TaskSignals  # noqa: E402
from formula_composer import (  # noqa: E402
    compose_chain,
    reset_registry_cache,
    score_all_roles,
)


@pytest.fixture(autouse=True)
def _reset():
    reset_registry_cache()
    yield
    reset_registry_cache()


# --- 1. Situation override --------------------------------------------------


def test_situation_override_wins_over_preset():
    sig = TaskSignals(
        domain=["backend"],
        action="create",
        urgency="normal",
        scope_size="medium",
        complexity="COMPLICATED",
    )
    chain = compose_chain(sig, situation_id="incident-response")
    assert chain.source == "situation"
    assert chain.situation_id == "incident-response"
    assert "debugger" in chain.chain


def test_unknown_situation_falls_through():
    sig = TaskSignals(
        domain=["backend"],
        action="create",
        scope_size="medium",
        complexity="COMPLICATED",
    )
    chain = compose_chain(sig, situation_id="no-such-situation")
    # Should fall through to preset or composer
    assert chain.source in ("preset", "composer", "fallback")


# --- 2. Preset match --------------------------------------------------------


def test_preset_schema_migration():
    sig = TaskSignals(
        domain=["db", "backend"],
        action="modify",
        breaking_change=True,
        scope_size="medium",
        complexity="COMPLICATED",
    )
    chain = compose_chain(sig)
    assert chain.source == "preset"
    assert chain.preset_id == "schema-migration"
    assert chain.chain == ["analyst", "architect", "security_auditor", "implementer", "reviewer"]
    assert chain.preset_version is not None and len(chain.preset_version) == 16


def test_preset_stamps_threshold():
    sig = TaskSignals(
        action="document",
        domain=["docs"],
        complexity="COMPLICATED",
    )
    chain = compose_chain(sig, preset_min_score=8)
    assert chain.effective_threshold == 8


def test_preset_external_integration():
    sig = TaskSignals(
        action="create",
        domain=["backend"],
        external_dependency=True,
        scope_size="medium",
        complexity="COMPLICATED",
    )
    chain = compose_chain(sig)
    # Should match external-integration preset (score 9 >= threshold 8)
    assert chain.source == "preset"
    assert chain.preset_id == "external-integration"


def test_preset_threshold_too_high_falls_through():
    sig = TaskSignals(
        action="create",
        domain=["backend"],
        external_dependency=True,
        scope_size="medium",
        complexity="COMPLICATED",
    )
    # Raise threshold above every preset's score
    chain = compose_chain(sig, preset_min_score=15)
    assert chain.source in ("composer", "fallback")


# --- 3. Composer fallback ---------------------------------------------------


def test_composer_produces_chain_when_no_preset():
    sig = TaskSignals(
        action="refactor",
        domain=["backend"],
        scope_size="small",
        complexity="COMPLICATED",
    )
    chain = compose_chain(sig, preset_min_score=14)  # force past presets
    assert chain.source in ("composer", "fallback")
    assert len(chain.chain) >= 1


def test_canonical_order_preserved():
    sig = TaskSignals(
        action="create",
        domain=["backend"],
        breaking_change=True,
        complexity="COMPLEX",
    )
    chain = compose_chain(sig)
    # Canonical order: roles must appear in the formula-1..11 sequence
    # (researcher → … → refactorer). Map name → ordinal, assert ordinals
    # are non-decreasing.
    canonical_order = [
        "researcher",
        "analyst",
        "architect",
        "documenter",
        "implementer",
        "reviewer",
        "debugger",
        "security_auditor",
        "deployer",
        "observer",
        "refactorer",
    ]
    indices = [canonical_order.index(r) for r in chain.chain]
    assert indices == sorted(indices), f"chain not in canonical order: {chain.chain}"


# --- 4. Hard fallback -------------------------------------------------------


def test_hard_fallback_never_empty():
    # A signal set that no preset matches + no roles score high enough
    sig = TaskSignals(
        action="unknown",
        domain=[],
        novelty=0.0,
        complexity="COMPLICATED",
    )
    chain = compose_chain(sig, preset_min_score=15)
    assert len(chain.chain) >= 1
    # Either composer scoring succeeds or hard fallback fires
    if chain.source == "fallback":
        assert chain.chain == ["analyst", "architect", "implementer", "reviewer"]


def test_hard_fallback_for_clear():
    sig = TaskSignals(
        action="unknown",
        complexity="CLEAR",
    )
    chain = compose_chain(sig, preset_min_score=15)
    if chain.source == "fallback":
        assert chain.chain == ["implementer", "reviewer"]


# --- 5. Role scoring primitives --------------------------------------------


def test_scoring_debug_incident():
    sig = TaskSignals(
        action="debug",
        urgency="incident",
        complexity="CHAOTIC",
    )
    activations = score_all_roles(sig)
    f7 = next(a for a in activations if a.role_id == "debugger")
    assert f7.score >= 5, f"debugger should fire strongly on debug+incident, got {f7.score}"


def test_scoring_research_deactivates_debug():
    sig = TaskSignals(
        action="research",
        complexity="COMPLEX",
    )
    activations = score_all_roles(sig)
    f7 = next(a for a in activations if a.role_id == "debugger")
    f1 = next(a for a in activations if a.role_id == "researcher")
    assert f1.score > f7.score, "researcher should beat debugger when action=research"


def test_presets_production_bug_mitigate_via_situation():
    # production-bug-mitigate preset uses urgency=incident
    sig = TaskSignals(
        action="debug",
        urgency="incident",
        complexity="CHAOTIC",
    )
    chain = compose_chain(sig)
    # Either preset production-bug-mitigate OR situation override wins
    assert chain.source in ("preset", "situation", "composer")
    assert "debugger" in chain.chain


def test_takeover_preset():
    sig = TaskSignals(
        is_takeover=True,
        action="modify",
        complexity="COMPLEX",
    )
    chain = compose_chain(sig)
    assert chain.source == "preset"
    assert chain.preset_id == "legacy-takeover"
    assert chain.chain[0] == "analyst"  # starts with analyst in reverse mode per formula spec


# --- 6. Parallel roles metadata --------------------------------------------


def test_security_audit_parallel():
    sig = TaskSignals(
        action="audit",
        domain=["security"],
        complexity="COMPLEX",
    )
    chain = compose_chain(sig)
    assert chain.source == "preset"
    assert chain.preset_id == "security-audit-full"
    assert "L5" in chain.parallel_roles


def test_audit_exhaustive_only_fires_with_exhaustive_intent():
    """audit-exhaustive must NOT shadow domain-specific audit presets — it is
    gated on exhaustive intent. A plain audit picks the domain preset; the
    same audit with exhaustive=True picks audit-exhaustive."""
    plain = compose_chain(TaskSignals(action="audit", domain=["security"], complexity="COMPLEX"))
    assert plain.preset_id == "security-audit-full"

    exhaustive = compose_chain(
        TaskSignals(action="audit", domain=["security"], complexity="COMPLEX", exhaustive=True)
    )
    assert exhaustive.preset_id == "audit-exhaustive"
