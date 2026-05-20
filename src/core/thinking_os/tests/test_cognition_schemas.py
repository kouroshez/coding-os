"""Tests for Phase M Pydantic IO contracts (cognition_schemas.py)."""

from __future__ import annotations

import pytest
from cognition_schemas import (
    Actor,
    AmbiguityCriterion,
    AnalystInput,
    AnalystOutput,
    ArchitectOutput,
    BacktrackEvent,
    DebuggerOutput,
    Discovery,
    EvidenceBundle,
    GoalNode,
    ImplementerOutput,
    NextAction,
    ResearcherOutput,
    ReviewerOutput,
    Scenario,
    SecurityAuditorOutput,
    SupervisorState,
)


class TestAmbiguityCriterion:
    def test_all_seven_criteria_exist(self):
        expected = {
            "observable",
            "measurable",
            "testable",
            "scoped",
            "owned",
            "reversible_or_justified",
            "connected_to_user_value",
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
        out = AnalystOutput(problem_statement="Users cannot reset passwords.")
        assert out.problem_statement
        assert out.actors == []
        assert out.unknowns == []

    def test_with_actors_and_scenarios(self):
        out = AnalystOutput(
            problem_statement="Add payment flow.",
            actors=[Actor(id="user", role="buyer", capabilities=["pay"])],
            scenarios=[
                Scenario(id="S1", given="user has card", when="checkout", then="payment succeeds")
            ],
        )
        assert len(out.actors) == 1
        assert len(out.scenarios) == 1


class TestF2Input:
    def test_default_intensity_steps(self):
        inp = AnalystInput(task_description="Add auth")
        assert inp.intensity_steps == list(range(1, 13))

    def test_optional_f1_research(self):
        inp = AnalystInput(task_description="Add auth", researcher=None)
        assert inp.researcher is None


class TestEvidenceBundle:
    def test_empty_bundle(self):
        bundle = EvidenceBundle(task_marker="feat-auth", persona_id="senior-backend")
        assert bundle.researcher is None
        assert bundle.analyst is None
        assert bundle.backtracks == []
        assert bundle.intensity == "standard"

    def test_bundle_accumulates(self):
        bundle = EvidenceBundle(task_marker="feat-auth", persona_id="senior-backend")
        bundle.researcher = ResearcherOutput(summary="Found OAuth2 patterns")
        bundle.analyst = AnalystOutput(problem_statement="Add OAuth2 login")
        assert bundle.researcher.summary == "Found OAuth2 patterns"
        assert bundle.analyst.problem_statement

    def test_degraded_formulas_list(self):
        bundle = EvidenceBundle(task_marker="t", persona_id="p")
        bundle.degraded_formulas.append("architect")
        assert "architect" in bundle.degraded_formulas

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
        s.dispatched.append("analyst")
        assert "analyst" in s.dispatched


class TestNextAction:
    def test_dispatch_action(self):
        action = NextAction(
            action="dispatch",
            formula="analyst",
            agent_file="src/core/thinking_os/agents/analyst.md",
        )
        assert action.action == "dispatch"
        assert action.formula == "analyst"

    def test_done_action(self):
        action = NextAction(action="done", reason="All formulas complete")
        assert action.action == "done"
        assert action.formulas == []

    def test_backtrack_action(self):
        action = NextAction(action="backtrack", formula="analyst", reason="Missing actor")
        assert action.action == "backtrack"


class TestBacktrackAndDiscovery:
    def test_backtrack_event(self):
        evt = BacktrackEvent(from_formula="architect", to_formula="analyst", reason="missing actor")
        assert evt.from_formula == "architect"

    def test_discovery_decision(self):
        d = Discovery(
            kind="new_requirement",
            summary="Found compliance constraint",
            impact_assessment="high — affects Architect security boundaries",
            decision="backtrack_now",
        )
        assert d.decision == "backtrack_now"


class TestOutputModelsPassOrFail:
    def test_f6_passed_default_true(self):
        out = ReviewerOutput()
        assert out.passed is True

    def test_f8_passed_default_true(self):
        out = SecurityAuditorOutput()
        assert out.passed is True

    def test_f7_root_cause_required(self):
        out = DebuggerOutput(root_cause="nil pointer dereference in auth.go:42")
        assert out.root_cause

    def test_f3_open_questions_optional(self):
        out = ArchitectOutput(selected_style="hexagonal")
        assert out.open_questions == []

    def test_f5_output_files_lists(self):
        out = ImplementerOutput(files_created=["src/new.py"], files_modified=["src/old.py"])
        assert "src/new.py" in out.files_created
