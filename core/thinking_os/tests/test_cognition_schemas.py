"""Tests for Phase M Pydantic IO contracts (cognition_schemas.py)."""

from __future__ import annotations

import pytest

from cognition_schemas import (
    AmbiguityCriterion,
    Actor,
    BacktrackEvent,
    Discovery,
    EvidenceBundle,
    F1Output,
    F2Input,
    F2Output,
    F3Output,
    F5Output,
    F6Output,
    F7Output,
    F8Output,
    GoalNode,
    NextAction,
    Scenario,
    SupervisorState,
)


class TestAmbiguityCriterion:
    def test_all_seven_criteria_exist(self):
        expected = {
            "observable", "measurable", "testable", "scoped",
            "owned", "reversible_or_justified", "connected_to_user_value",
        }
        assert {c.value for c in AmbiguityCriterion} == expected

    def test_is_str_enum(self):
        assert isinstance(AmbiguityCriterion.SCOPED, str)
        assert AmbiguityCriterion.SCOPED == "scoped"


class TestGoalNodeRecursion:
    def test_nested_goal_nodes(self):
        root = GoalNode(
            id="root",
            description="Top-level goal",
            children=[GoalNode(id="child-1", description="Sub-goal")],
        )
        assert root.children[0].id == "child-1"

    def test_empty_children_default(self):
        node = GoalNode(id="leaf", description="Leaf goal")
        assert node.children == []


class TestF2Output:
    def test_minimal_valid(self):
        out = F2Output(problem_statement="Users cannot reset passwords.")
        assert out.problem_statement
        assert out.actors == []
        assert out.unknowns == []

    def test_with_actors_and_scenarios(self):
        out = F2Output(
            problem_statement="Add payment flow.",
            actors=[Actor(id="user", role="buyer", capabilities=["pay"])],
            scenarios=[Scenario(id="S1", given="user has card", when="checkout", then="payment succeeds")],
        )
        assert len(out.actors) == 1
        assert len(out.scenarios) == 1


class TestF2Input:
    def test_default_intensity_steps(self):
        inp = F2Input(task_description="Add auth")
        assert inp.intensity_steps == list(range(1, 13))

    def test_optional_f1_research(self):
        inp = F2Input(task_description="Add auth", f1_research=None)
        assert inp.f1_research is None


class TestEvidenceBundle:
    def test_empty_bundle(self):
        bundle = EvidenceBundle(task_marker="feat-auth", persona_id="senior-backend")
        assert bundle.F1_research is None
        assert bundle.F2_decompose is None
        assert bundle.backtracks == []
        assert bundle.intensity == "standard"

    def test_bundle_accumulates(self):
        bundle = EvidenceBundle(task_marker="feat-auth", persona_id="senior-backend")
        bundle.F1_research = F1Output(summary="Found OAuth2 patterns")
        bundle.F2_decompose = F2Output(problem_statement="Add OAuth2 login")
        assert bundle.F1_research.summary == "Found OAuth2 patterns"
        assert bundle.F2_decompose.problem_statement

    def test_degraded_formulas_list(self):
        bundle = EvidenceBundle(task_marker="t", persona_id="p")
        bundle.degraded_formulas.append("F3")
        assert "F3" in bundle.degraded_formulas

    def test_situation_id_optional(self):
        bundle = EvidenceBundle(task_marker="t", persona_id="p", situation_id="incident-response")
        assert bundle.situation_id == "incident-response"


class TestSupervisorState:
    def test_default_phase_idle(self):
        s = SupervisorState(session_id="ses-1", task_marker="t", persona_id="tech-lead")
        assert s.phase == "IDLE"
        assert s.backtrack_count == 0

    def test_dispatched_list(self):
        s = SupervisorState(session_id="ses-1", task_marker="t", persona_id="tech-lead")
        s.dispatched.append("F2")
        assert "F2" in s.dispatched


class TestNextAction:
    def test_dispatch_action(self):
        action = NextAction(action="dispatch", formula="F2", agent_file="core/thinking_os/agents/F2_decompose.md")
        assert action.action == "dispatch"
        assert action.formula == "F2"

    def test_done_action(self):
        action = NextAction(action="done", reason="All formulas complete")
        assert action.action == "done"
        assert action.formulas == []

    def test_backtrack_action(self):
        action = NextAction(action="backtrack", formula="F2", reason="Missing actor")
        assert action.action == "backtrack"


class TestBacktrackAndDiscovery:
    def test_backtrack_event(self):
        evt = BacktrackEvent(from_formula="F3", to_formula="F2", reason="missing actor")
        assert evt.from_formula == "F3"

    def test_discovery_decision(self):
        d = Discovery(
            kind="new_requirement",
            summary="Found compliance constraint",
            impact_assessment="high — affects F3 security boundaries",
            decision="backtrack_now",
        )
        assert d.decision == "backtrack_now"


class TestOutputModelsPassOrFail:
    def test_f6_passed_default_true(self):
        out = F6Output()
        assert out.passed is True

    def test_f8_passed_default_true(self):
        out = F8Output()
        assert out.passed is True

    def test_f7_root_cause_required(self):
        out = F7Output(root_cause="nil pointer dereference in auth.go:42")
        assert out.root_cause

    def test_f3_open_questions_optional(self):
        out = F3Output(selected_style="hexagonal")
        assert out.open_questions == []

    def test_f5_output_files_lists(self):
        out = F5Output(files_created=["src/new.py"], files_modified=["src/old.py"])
        assert "src/new.py" in out.files_created
