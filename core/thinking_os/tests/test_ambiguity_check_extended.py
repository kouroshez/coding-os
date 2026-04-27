"""Tests for ambiguity_check coverage of F1..F11 (Wave 0 C1)."""
from __future__ import annotations

from cognition import ambiguity_check
from cognition_schemas import (
    EvidenceBundle, F1Output, F2Output, F3Output, F4Output, F5Output,
    F6Output, F7Output, F8Output, F9Output, F10Output, F11Output,
)


def _bundle(**fields) -> EvidenceBundle:
    fields.setdefault("task_marker", "test-task")
    fields.setdefault("persona_id", "test-persona")
    return EvidenceBundle(**fields)


# --- happy path: a fully populated formula passes its criteria ---

def test_f1_passes_when_sources_and_findings_present():
    out = F1Output(
        summary="x",
        sources=[{"title": "a", "url_or_path": "p"}],
        key_findings=["f1"],
        recommended_next="proceed",
    )
    v = ambiguity_check(_bundle(F1_research=out))
    assert all(item["formula"] != "F1" for item in v), v


def test_f2_passes_with_full_evidence():
    out = F2Output(
        problem_statement="p",
        scope_in=["x"],
        actors=[{"id": "a1", "role": "user"}],
        success_metrics=[{"name": "n", "target": "t", "measurement": "m"}],
        scenarios=[{
            "id": "s1", "given": "g", "when": "w", "then": "t",
        }],
    )
    v = ambiguity_check(_bundle(F2_decompose=out))
    assert all(item["formula"] != "F2" for item in v), v


# --- empty paths: each formula raises its declared violations ---

def test_f1_empty_violates_observable_and_scoped():
    v = ambiguity_check(_bundle(F1_research=F1Output(summary="x")))
    keys = {(i["formula"], i["criterion"]) for i in v}
    assert ("F1", "observable") in keys
    assert ("F1", "scoped") in keys


def test_f3_empty_violates_all_three():
    v = ambiguity_check(_bundle(F3_architect=F3Output(selected_style="")))
    keys = {(i["formula"], i["criterion"]) for i in v}
    assert ("F3", "scoped") in keys
    assert ("F3", "measurable") in keys
    assert ("F3", "reversible_or_justified") in keys


def test_f5_empty_violates_three():
    v = ambiguity_check(_bundle(F5_implement=F5Output()))
    keys = {(i["formula"], i["criterion"]) for i in v}
    assert ("F5", "testable") in keys
    assert ("F5", "scoped") in keys
    assert ("F5", "owned") in keys


def test_f6_empty_violates_measurable_and_testable():
    v = ambiguity_check(_bundle(F6_test_review=F6Output()))
    keys = {(i["formula"], i["criterion"]) for i in v}
    assert ("F6", "measurable") in keys
    assert ("F6", "testable") in keys


def test_f7_empty_violates_three():
    v = ambiguity_check(_bundle(F7_debug=F7Output(root_cause="")))
    keys = {(i["formula"], i["criterion"]) for i in v}
    assert ("F7", "observable") in keys
    assert ("F7", "testable") in keys
    assert ("F7", "scoped") in keys


def test_f8_empty_violates_three():
    v = ambiguity_check(_bundle(F8_security=F8Output()))
    keys = {(i["formula"], i["criterion"]) for i in v}
    assert ("F8", "observable") in keys
    assert ("F8", "scoped") in keys
    assert ("F8", "owned") in keys


def test_f9_empty_violates_three():
    v = ambiguity_check(_bundle(F9_deploy=F9Output()))
    keys = {(i["formula"], i["criterion"]) for i in v}
    assert ("F9", "reversible_or_justified") in keys
    assert ("F9", "testable") in keys
    assert ("F9", "observable") in keys


def test_f10_empty_violates_two():
    v = ambiguity_check(_bundle(F10_monitor=F10Output()))
    keys = {(i["formula"], i["criterion"]) for i in v}
    assert ("F10", "measurable") in keys
    assert ("F10", "observable") in keys


def test_f11_empty_violates_three():
    v = ambiguity_check(_bundle(F11_refactor=F11Output()))
    keys = {(i["formula"], i["criterion"]) for i in v}
    assert ("F11", "scoped") in keys
    assert ("F11", "measurable") in keys
    assert ("F11", "testable") in keys


# --- empty bundle: no formula dispatched → no violations ---

def test_empty_bundle_yields_no_violations():
    v = ambiguity_check(_bundle())
    assert v == []


# --- partial bundle: only checks dispatched formulas ---

def test_only_dispatched_formula_is_checked():
    v = ambiguity_check(_bundle(F11_refactor=F11Output()))
    # F11 violations only — F1..F10 not present
    assert all(i["formula"] == "F11" for i in v)
