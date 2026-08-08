"""Tests for ambiguity_check coverage of all formula roles (Wave 0 C1)."""

from __future__ import annotations

from cognition import ambiguity_check
from cognition_schemas import (
    AnalystOutput,
    ArchitectOutput,
    DebuggerOutput,
    DeployerOutput,
    EvidenceBundle,
    ImplementerOutput,
    ObserverOutput,
    RefactorerOutput,
    ResearcherOutput,
    ReviewerOutput,
    SecurityAuditorOutput,
)


def _bundle(**fields) -> EvidenceBundle:
    fields.setdefault("task_marker", "test-task")
    fields.setdefault("persona_id", "test-persona")
    return EvidenceBundle(**fields)


# --- happy path: a fully populated formula passes its criteria ---


def test_f1_passes_when_sources_and_findings_present():
    out = ResearcherOutput(
        summary="x",
        sources=[{"title": "a", "url_or_path": "p"}],
        key_findings=["f1"],
        recommended_next="proceed",
    )
    v = ambiguity_check(_bundle(researcher=out))
    assert all(item["formula"] != "researcher" for item in v), v


def test_f2_passes_with_full_evidence():
    out = AnalystOutput(
        problem_statement="p",
        scope_in=["x"],
        actors=[{"id": "a1", "role": "user"}],
        success_metrics=[{"name": "n", "target": "t", "measurement": "m"}],
        scenarios=[
            {
                "id": "s1",
                "given": "g",
                "when": "w",
                "then": "t",
            }
        ],
    )
    v = ambiguity_check(_bundle(analyst=out))
    assert all(item["formula"] != "analyst" for item in v), v


# --- empty paths: each formula raises its declared violations ---


def test_f1_empty_violates_observable_and_scoped():
    v = ambiguity_check(_bundle(researcher=ResearcherOutput(summary="x")))
    keys = {(i["formula"], i["criterion"]) for i in v}
    assert ("researcher", "observable") in keys
    assert ("researcher", "scoped") in keys


def test_f3_empty_violates_all_three():
    v = ambiguity_check(_bundle(architect=ArchitectOutput(selected_style="")))
    keys = {(i["formula"], i["criterion"]) for i in v}
    assert ("architect", "scoped") in keys
    assert ("architect", "measurable") in keys
    assert ("architect", "reversible_or_justified") in keys


def test_f5_empty_violates_three():
    v = ambiguity_check(_bundle(implementer=ImplementerOutput()))
    keys = {(i["formula"], i["criterion"]) for i in v}
    assert ("implementer", "testable") in keys
    assert ("implementer", "scoped") in keys
    assert ("implementer", "owned") in keys


def test_f6_empty_violates_measurable_and_testable():
    v = ambiguity_check(_bundle(reviewer=ReviewerOutput()))
    keys = {(i["formula"], i["criterion"]) for i in v}
    assert ("reviewer", "measurable") in keys
    assert ("reviewer", "testable") in keys


def test_f7_empty_violates_three():
    v = ambiguity_check(_bundle(debugger=DebuggerOutput(root_cause="")))
    keys = {(i["formula"], i["criterion"]) for i in v}
    assert ("debugger", "observable") in keys
    assert ("debugger", "testable") in keys
    assert ("debugger", "scoped") in keys


def test_f8_empty_violates_three():
    v = ambiguity_check(_bundle(security_auditor=SecurityAuditorOutput()))
    keys = {(i["formula"], i["criterion"]) for i in v}
    assert ("security_auditor", "observable") in keys
    assert ("security_auditor", "scoped") in keys
    assert ("security_auditor", "owned") in keys


def test_f9_empty_violates_three():
    v = ambiguity_check(_bundle(deployer=DeployerOutput()))
    keys = {(i["formula"], i["criterion"]) for i in v}
    assert ("deployer", "reversible_or_justified") in keys
    assert ("deployer", "testable") in keys
    assert ("deployer", "observable") in keys


def test_f10_empty_violates_two():
    v = ambiguity_check(_bundle(observer=ObserverOutput()))
    keys = {(i["formula"], i["criterion"]) for i in v}
    assert ("observer", "measurable") in keys
    assert ("observer", "observable") in keys


def test_f11_empty_violates_three():
    v = ambiguity_check(_bundle(refactorer=RefactorerOutput()))
    keys = {(i["formula"], i["criterion"]) for i in v}
    assert ("refactorer", "scoped") in keys
    assert ("refactorer", "measurable") in keys
    assert ("refactorer", "testable") in keys


# --- empty bundle: no formula dispatched → no violations ---


def test_empty_bundle_yields_no_violations():
    v = ambiguity_check(_bundle())
    assert v == []


# --- partial bundle: only checks dispatched formulas ---


def test_only_dispatched_formula_is_checked():
    v = ambiguity_check(_bundle(refactorer=RefactorerOutput()))
    # Refactorer violations only — other roles not present
    assert all(i["formula"] == "refactorer" for i in v)
