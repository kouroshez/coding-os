"""Tests for the supervisor state machine (cognition.py)."""

from __future__ import annotations

import pytest
from cognition import (
    advance,
    ambiguity_check,
    apply_backtrack,
    build_input_slice,
    input_hash,
    load_agent_registry,
    load_situation_registry,
)
from cognition_schemas import (
    Actor,
    AnalystOutput,
    ArchitectOutput,
    EvidenceBundle,
    ResearcherOutput,
    Scenario,
    SupervisorState,
)

# ---------------------------------------------------------------------------
# Registry loading tests
# ---------------------------------------------------------------------------


class TestRegistries:
    def test_situation_registry_loads(self):
        reg = load_situation_registry()
        assert "incident-response" in reg
        assert "onboarding" in reg
        assert "existing-project-takeover" in reg

    def test_situation_registry_has_6_entries(self):
        reg = load_situation_registry()
        assert len(reg) == 6

    def test_agent_registry_loads(self):
        reg = load_agent_registry()
        for fid in [
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
        ]:
            assert fid in reg, f"Missing agent file for {fid}"

    def test_agent_registry_has_11_formulas(self):
        reg = load_agent_registry()
        assert len(reg) == 11


# ---------------------------------------------------------------------------
# Supervisor state machine tests
# ---------------------------------------------------------------------------


def _make_state(**kwargs) -> SupervisorState:
    defaults = dict(session_id="ses-test-1", task_marker="feat-auth", persona_id="senior-backend")
    defaults.update(kwargs)
    return SupervisorState(**defaults)


def _make_bundle(**kwargs) -> EvidenceBundle:
    defaults = dict(task_marker="feat-auth", persona_id="senior-backend")
    defaults.update(kwargs)
    return EvidenceBundle(**defaults)


class TestSupervisorAdvance:
    def test_idle_returns_classify(self):
        state = _make_state(phase="IDLE")
        bundle = _make_bundle()
        action = advance(state, bundle)
        assert action.action == "classify"
        assert state.phase == "CLASSIFYING"

    def test_routing_builds_queue_and_dispatches(self):
        # persona_id carries a composer-derived chain.
        state = _make_state(
            phase="ROUTING", persona_id="chain:analyst,architect,implementer,reviewer"
        )
        bundle = _make_bundle(persona_id="chain:analyst,architect,implementer,reviewer")
        action = advance(state, bundle)
        assert action.action == "dispatch"
        assert action.formula is not None

    def test_dispatch_advances_through_chain(self):
        state = _make_state(phase="ROUTING", persona_id="chain:implementer,reviewer")
        bundle = _make_bundle(persona_id="chain:implementer,reviewer")
        action1 = advance(state, bundle)
        assert action1.action == "dispatch"
        state.dispatched.append(action1.formula)
        state.phase = "DISPATCHING"
        action2 = advance(state, bundle)
        assert action2.action in ("dispatch", "done")

    def test_done_when_all_dispatched(self):
        state = _make_state(phase="DISPATCHING", persona_id="chain:implementer,reviewer")
        state.dispatched = ["implementer", "reviewer"]
        state.pending = ["implementer", "reviewer"]
        bundle = _make_bundle(persona_id="chain:implementer,reviewer")
        action = advance(state, bundle)
        assert action.action == "done"

    def test_situation_overrides_persona(self):
        state = _make_state(
            phase="ROUTING",
            persona_id="devops",
            situation_id="onboarding",
        )
        bundle = _make_bundle(situation_id="onboarding")
        action = advance(state, bundle)
        assert action.action == "dispatch"
        assert action.formula == "implementer"


class TestApplyBacktrack:
    def test_backtrack_increments_count(self):
        state = _make_state(phase="DISPATCHING")
        state.dispatched = ["analyst", "architect"]
        action = apply_backtrack(state, "architect", "analyst")
        assert action.action == "backtrack"
        assert state.backtrack_count == 1

    def test_backtrack_clears_downstream(self):
        state = _make_state(phase="DISPATCHING")
        state.dispatched = ["analyst", "architect", "implementer"]
        apply_backtrack(state, "implementer", "analyst")
        assert "architect" not in state.dispatched
        assert "implementer" not in state.dispatched

    def test_anti_paralysis_advisory_at_3(self):
        state = _make_state(phase="DISPATCHING")
        state.backtrack_count = 2
        state.dispatched = ["analyst"]
        action = apply_backtrack(state, "analyst", "researcher")
        assert "Anti-Paralysis" in action.advisory

    def test_anti_paralysis_stronger_at_5(self):
        state = _make_state(phase="DISPATCHING")
        state.backtrack_count = 4
        state.dispatched = ["analyst"]
        action = apply_backtrack(state, "analyst", "researcher")
        assert "Anti-Paralysis" in action.advisory


# ---------------------------------------------------------------------------
# EvidenceBundle input slice tests
# ---------------------------------------------------------------------------


class TestBuildInputSlice:
    def test_f3_gets_f1_and_f2(self):
        bundle = _make_bundle()
        bundle.researcher = ResearcherOutput(summary="Research done")
        bundle.analyst = AnalystOutput(problem_statement="Add auth")
        slice_data = build_input_slice("architect", bundle)
        assert "researcher" in slice_data
        assert "analyst" in slice_data
        assert "architect" not in slice_data

    def test_f2_gets_f1_only(self):
        bundle = _make_bundle()
        bundle.researcher = ResearcherOutput(summary="Research done")
        bundle.analyst = AnalystOutput(problem_statement="Add auth")
        slice_data = build_input_slice("analyst", bundle)
        assert "researcher" in slice_data
        assert "analyst" not in slice_data

    def test_input_hash_deterministic(self):
        bundle = _make_bundle()
        bundle.researcher = ResearcherOutput(summary="Research done")
        s1 = build_input_slice("analyst", bundle)
        s2 = build_input_slice("analyst", bundle)
        assert input_hash(s1) == input_hash(s2)

    def test_different_bundles_different_hash(self):
        b1 = _make_bundle()
        b1.researcher = ResearcherOutput(summary="Research A")
        b2 = _make_bundle()
        b2.researcher = ResearcherOutput(summary="Research B")
        assert input_hash(build_input_slice("analyst", b1)) != input_hash(
            build_input_slice("analyst", b2)
        )


# ---------------------------------------------------------------------------
# Ambiguity gate tests
# ---------------------------------------------------------------------------


class TestAmbiguityCheck:
    def test_empty_bundle_no_violations(self):
        bundle = _make_bundle()
        violations = ambiguity_check(bundle)
        assert violations == []

    def test_f2_with_actors_no_owned_violation(self):
        bundle = _make_bundle()
        bundle.analyst = AnalystOutput(
            problem_statement="Add auth",
            actors=[Actor(id="user", role="buyer")],
            scope_in=["login flow"],
            scenarios=[Scenario(id="S1", given="g", when="w", then="t")],
        )
        violations = ambiguity_check(bundle)
        owned_violations = [v for v in violations if v["criterion"] == "owned"]
        assert owned_violations == []

    def test_f2_missing_actors_flags_owned(self):
        bundle = _make_bundle()
        bundle.analyst = AnalystOutput(
            problem_statement="Add auth",
            actors=[],
        )
        violations = ambiguity_check(bundle)
        owned_v = [v for v in violations if v["criterion"] == "owned"]
        assert len(owned_v) > 0

    def test_f2_missing_scope_flags_scoped(self):
        bundle = _make_bundle()
        bundle.analyst = AnalystOutput(
            problem_statement="Add auth",
            scope_in=[],
        )
        violations = ambiguity_check(bundle)
        scoped_v = [v for v in violations if v["criterion"] == "scoped"]
        assert len(scoped_v) > 0
