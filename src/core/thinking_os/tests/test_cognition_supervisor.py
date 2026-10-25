"""Tests for the supervisor state machine (cognition.py)."""

from __future__ import annotations

from cognition import (
    advance,
    build_input_slice,
    input_hash,
    load_agent_registry,
)
from cognition_schemas import (
    AnalystOutput,
    EvidenceBundle,
    ResearcherOutput,
    SupervisorState,
)

# ---------------------------------------------------------------------------
# Registry loading tests
# ---------------------------------------------------------------------------


class TestRegistries:
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

    def test_agent_registry_has_expected_roles(self):
        reg = load_agent_registry()
        # 11 composable formula roles + dispatch-only cards: repairer, distiller.
        assert len(reg) == 13
        assert "repairer" in reg
        assert "distiller" in reg


# ---------------------------------------------------------------------------
# Supervisor state machine tests
# ---------------------------------------------------------------------------


def _make_state(**kwargs) -> SupervisorState:
    defaults = {
        "session_id": "ses-test-1",
        "task_marker": "feat-auth",
        "persona_id": "senior-backend",
    }
    defaults.update(kwargs)
    return SupervisorState(**defaults)


def _make_bundle(**kwargs) -> EvidenceBundle:
    defaults = {"task_marker": "feat-auth", "persona_id": "senior-backend"}
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
