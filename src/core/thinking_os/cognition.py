"""Coding OS — Formula-agent supervisor (Phase M)."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

import yaml

from cognition_schemas import (
    AmbiguityCriterion,
    EvidenceBundle,
    NextAction,
    SupervisorState,
)

logger = logging.getLogger("coding_os.cognition")

# ---------------------------------------------------------------------------
# Registry paths
# ---------------------------------------------------------------------------

_HERE = Path(__file__).resolve().parent
AGENTS_DIR = _HERE / "agents"
SITUATIONS_DIR = _HERE / "situations"

# ---------------------------------------------------------------------------
# Registry loaders (cached at module level after first load)
# ---------------------------------------------------------------------------

_situation_registry: dict[str, dict[str, Any]] | None = None
_agent_registry: dict[str, dict[str, Any]] | None = None


def _load_yaml(path: Path) -> Any:
    with path.open() as fh:
        return yaml.safe_load(fh)


def load_situation_registry() -> dict[str, dict[str, Any]]:
    global _situation_registry
    if _situation_registry is None:
        reg = _load_yaml(SITUATIONS_DIR / "registry.yaml")
        _situation_registry = {s["id"]: s for s in reg.get("situations", [])}
    return _situation_registry


def load_agent_registry() -> dict[str, dict[str, Any]]:
    global _agent_registry
    if _agent_registry is not None:
        return _agent_registry
    registry: dict[str, dict[str, Any]] = {}
    for agent_file in sorted(AGENTS_DIR.glob("*.md")):
        if agent_file.name == "README.md":
            continue
        text = agent_file.read_text()
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 3:
                meta = yaml.safe_load(parts[1]) or {}
                fid = meta.get("id", agent_file.stem)
                meta["_file"] = agent_file.name
                registry[str(fid)] = meta
    _agent_registry = registry
    return _agent_registry


# ---------------------------------------------------------------------------
# Intensity helpers
# ---------------------------------------------------------------------------

_INTENSITY_ORDER = ("light", "standard", "full")

def _intensity_gte(a: str, b: str) -> bool:
    return _INTENSITY_ORDER.index(a) >= _INTENSITY_ORDER.index(b)


def _formulas_for_intensity(persona: dict[str, Any], intensity: str) -> list[str]:
    """Return primary + secondary formulas based on intensity level."""
    primary = persona.get("primary_formulas", [])
    secondary = persona.get("secondary_formulas", [])
    if _intensity_gte(intensity, "full"):
        return list(primary) + list(secondary)
    return list(primary)


def _intensity_steps(formula_id: str, intensity: str) -> list[int]:
    """Return the step list for a given formula at the requested intensity."""
    agents = load_agent_registry()
    meta = agents.get(formula_id, {})
    steps = meta.get("intensity_steps", {})
    if intensity in steps:
        return list(steps[intensity])
    # default: all steps 1-12
    return list(range(1, 13))


# ---------------------------------------------------------------------------
# Situation helpers
# ---------------------------------------------------------------------------

def _situation_dispatch_chain(situation_id: str) -> list[str]:
    """Return ordered formula IDs for a situation (non-formula actions skipped)."""
    situations = load_situation_registry()
    sit = situations.get(situation_id, {})
    chain = []
    for step in sit.get("dispatch_chain", []):
        if "dispatch" in step:
            chain.append(str(step["dispatch"]))
    return chain


# ---------------------------------------------------------------------------
# EvidenceBundle helpers
# ---------------------------------------------------------------------------

_FORMULA_BUNDLE_FIELD = {
    "researcher": "researcher",
    "analyst": "analyst",
    "architect": "architect",
    "documenter": "documenter",
    "implementer": "implementer",
    "reviewer": "reviewer",
    "debugger": "debugger",
    "security_auditor": "security_auditor",
    "deployer": "deployer",
    "observer": "observer",
    "refactorer": "refactorer",
}


def build_input_slice(formula_id: str, bundle: EvidenceBundle) -> dict[str, Any]:
    upstream: dict[str, Any] = {
        "task_description": bundle.task_marker,
        "intensity_steps": _intensity_steps(formula_id, bundle.intensity),
    }
    order = list(_FORMULA_BUNDLE_FIELD.keys())
    my_idx = order.index(formula_id) if formula_id in order else len(order)
    for i, fid in enumerate(order):
        if i >= my_idx:
            break
        field = _FORMULA_BUNDLE_FIELD[fid]
        val = getattr(bundle, field, None)
        if val is not None:
            upstream[field] = val.model_dump()
    return upstream


def input_hash(slice_data: dict[str, Any]) -> str:
    raw = json.dumps(slice_data, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Supervisor state machine
# ---------------------------------------------------------------------------

def advance(
    state: SupervisorState,
    bundle: EvidenceBundle,
) -> NextAction:
    if state.phase == "IDLE":
        state.phase = "CLASSIFYING"
        return NextAction(action="classify", reason="Gate not yet recorded")

    if state.phase == "CLASSIFYING":
        # Once gate is recorded externally, caller sets phase=ROUTING.
        return NextAction(action="classify", reason="Awaiting gate recording")

    if state.phase in ("ROUTING", "DISPATCHING", "INTEGRATING"):
        return _next_dispatch(state, bundle)

    if state.phase == "AWAITING_AGENT":
        # Caller records output and sets phase back to INTEGRATING.
        return NextAction(
            action="dispatch",
            formula=state.dispatched[-1] if state.dispatched else None,
            reason="Awaiting formula output",
        )

    # DONE
    return NextAction(action="done", reason="All formulas dispatched")


def _next_dispatch(
    state: SupervisorState,
    bundle: EvidenceBundle,
) -> NextAction:
    """Determine which formula to dispatch next, or signal done."""
    # Build pending queue on first routing call
    if not state.pending and state.phase == "ROUTING":
        state.pending = _build_queue(state)
        state.phase = "DISPATCHING"

    # Skip already-dispatched
    remaining = [f for f in state.pending if f not in state.dispatched]
    if not remaining:
        state.phase = "DONE"
        return NextAction(action="done", reason="All formulas complete")

    formula_id = remaining[0]
    agents = load_agent_registry()
    meta = agents.get(formula_id, {})
    agent_file = meta.get("_file", f"{formula_id}.md")

    slice_data = build_input_slice(formula_id, bundle)

    # Check for parallelisable formulas (security_auditor layers)
    parallel = meta.get("parallel_siblings", [])
    parallel_available = [
        f for f in parallel
        if f not in state.dispatched and f in remaining
    ]
    if parallel_available:
        all_parallel = [formula_id] + parallel_available
        state.phase = "AWAITING_AGENT"
        return NextAction(
            action="dispatch_parallel",
            formulas=all_parallel,
            input_slice=slice_data,
            agent_file=agent_file,
            reason=f"Parallel dispatch: {', '.join(all_parallel)}",
        )

    state.phase = "AWAITING_AGENT"
    return NextAction(
        action="dispatch",
        formula=formula_id,
        input_slice=slice_data,
        agent_file=f"src/core/thinking_os/agents/{agent_file}",
        reason=f"Next in chain: {formula_id}",
    )


def _build_queue(state: SupervisorState) -> list[str]:
    """
    Build the ordered dispatch queue.

    Priority (Phase N composer chain):
      1. If state.pending already set by caller (composer chain) → use as-is.
      2. If state.situation_id set → situation dispatch chain.
      3. If persona_id starts with "chain:" (composer output) → that chain.
      4. Empty list (caller is expected to use cos_compose_chain first).
    """
    if state.pending:
        return list(state.pending)

    if state.situation_id:
        chain = _situation_dispatch_chain(state.situation_id)
        if chain:
            return chain

    # Phase N — caller passed a composer-derived role chain as persona_id?
    # Format: "chain:analyst,architect,implementer,reviewer" (supported by task-start.sh)
    if state.persona_id.startswith("chain:"):
        return [r.strip() for r in state.persona_id[6:].split(",") if r.strip()]

    return []


# ---------------------------------------------------------------------------
# Backtrack helper
# ---------------------------------------------------------------------------

def apply_backtrack(
    state: SupervisorState,
    from_formula: str,
    to_formula: str,
) -> NextAction:
    state.backtrack_count += 1
    # Remove from_formula and all formulas after to_formula from dispatched
    order = list(_FORMULA_BUNDLE_FIELD.keys())
    to_idx = order.index(to_formula) if to_formula in order else 0
    state.dispatched = [f for f in state.dispatched if order.index(f) < to_idx]
    state.phase = "DISPATCHING"

    advisory = ""
    if state.backtrack_count >= 5:
        advisory = (
            f"Anti-Paralysis: {state.backtrack_count} backtracks this session. "
            "Consider narrowing task scope or raising intensity level."
        )
    elif state.backtrack_count >= 3:
        advisory = (
            f"Anti-Paralysis: {state.backtrack_count} backtracks. "
            "Review scope if pattern continues."
        )

    return NextAction(
        action="backtrack",
        formula=to_formula,
        reason=f"{from_formula} signalled backtrack to {to_formula}",
        advisory=advisory,
    )


# ---------------------------------------------------------------------------
# Anti-Ambiguity gate
# ---------------------------------------------------------------------------

# Per-formula required criteria. Each formula's output schema determines
# which fields are evidence for which criterion (see _CRITERIA_FIELD_MAP).
_CRITERIA_WEIGHTS: dict[str, list[AmbiguityCriterion]] = {
    "researcher": [
        AmbiguityCriterion.OBSERVABLE,
        AmbiguityCriterion.SCOPED,
    ],
    "analyst": [
        AmbiguityCriterion.SCOPED,
        AmbiguityCriterion.OWNED,
        AmbiguityCriterion.OBSERVABLE,
        AmbiguityCriterion.TESTABLE,
    ],
    "architect": [
        AmbiguityCriterion.SCOPED,
        AmbiguityCriterion.MEASURABLE,
        AmbiguityCriterion.REVERSIBLE_OR_JUSTIFIED,
    ],
    "documenter": [
        AmbiguityCriterion.OBSERVABLE,
        AmbiguityCriterion.SCOPED,
    ],
    "implementer": [
        AmbiguityCriterion.TESTABLE,
        AmbiguityCriterion.SCOPED,
        AmbiguityCriterion.OWNED,
    ],
    "reviewer": [
        AmbiguityCriterion.MEASURABLE,
        AmbiguityCriterion.TESTABLE,
    ],
    "debugger": [
        AmbiguityCriterion.OBSERVABLE,
        AmbiguityCriterion.TESTABLE,
        AmbiguityCriterion.SCOPED,
    ],
    "security_auditor": [
        AmbiguityCriterion.OBSERVABLE,
        AmbiguityCriterion.SCOPED,
        AmbiguityCriterion.OWNED,
    ],
    "deployer": [
        AmbiguityCriterion.REVERSIBLE_OR_JUSTIFIED,
        AmbiguityCriterion.TESTABLE,
        AmbiguityCriterion.OBSERVABLE,
    ],
    "observer": [
        AmbiguityCriterion.MEASURABLE,
        AmbiguityCriterion.OBSERVABLE,
    ],
    "refactorer": [
        AmbiguityCriterion.SCOPED,
        AmbiguityCriterion.MEASURABLE,
        AmbiguityCriterion.TESTABLE,
    ],
}


# Maps (formula_id, criterion) → tuple of (field_name, detail_when_missing).
# A criterion passes when at least one of its mapped fields is non-empty.
# When multiple fields map to one criterion, ANY non-empty satisfies. Detail
# message describes the missing evidence for the agent to fix.
_CRITERIA_FIELD_MAP: dict[str, dict[AmbiguityCriterion, tuple[tuple[str, str], ...]]] = {
    "researcher": {
        AmbiguityCriterion.OBSERVABLE: (("sources", "No sources cited in Researcher output"),),
        AmbiguityCriterion.SCOPED: (
            ("key_findings", "No key_findings recorded in Researcher output"),
            ("recommended_next", "recommended_next is empty in Researcher output"),
        ),
    },
    "analyst": {
        AmbiguityCriterion.SCOPED: (("scope_in", "scope_in is empty in Analyst output"),),
        AmbiguityCriterion.OWNED: (("actors", "No actors defined in Analyst output"),),
        AmbiguityCriterion.OBSERVABLE: (("success_metrics", "No success_metrics in Analyst output"),),
        AmbiguityCriterion.TESTABLE: (("scenarios", "No scenarios defined in Analyst output"),),
    },
    "architect": {
        AmbiguityCriterion.SCOPED: (("selected_style", "selected_style empty in Architect output"),),
        AmbiguityCriterion.MEASURABLE: (("nfr_targets", "No NFR targets recorded in Architect output"),),
        AmbiguityCriterion.REVERSIBLE_OR_JUSTIFIED: (("adrs", "No ADRs recorded in Architect output"),),
    },
    "documenter": {
        AmbiguityCriterion.OBSERVABLE: (
            ("docs_created", "No docs_created in Documenter output"),
            ("docs_updated", "No docs_updated in Documenter output"),
        ),
        AmbiguityCriterion.SCOPED: (("changelog_entry", "changelog_entry empty in Documenter output"),),
    },
    "implementer": {
        AmbiguityCriterion.TESTABLE: (
            ("files_created", "No files_created in Implementer output"),
            ("files_modified", "No files_modified in Implementer output"),
        ),
        AmbiguityCriterion.SCOPED: (("implementation_notes", "implementation_notes empty in Implementer output"),),
        AmbiguityCriterion.OWNED: (("open_items", "open_items unset (None) in Implementer output"),),
    },
    "reviewer": {
        AmbiguityCriterion.MEASURABLE: (("coverage_summary", "No coverage_summary in Reviewer output"),),
        AmbiguityCriterion.TESTABLE: (("test_cases", "No test_cases in Reviewer output"),),
    },
    "debugger": {
        AmbiguityCriterion.OBSERVABLE: (("root_cause", "root_cause empty in Debugger output"),),
        AmbiguityCriterion.TESTABLE: (("regression_tests_added", "No regression tests in Debugger output"),),
        AmbiguityCriterion.SCOPED: (("fix_applied", "fix_applied empty in Debugger output"),),
    },
    "security_auditor": {
        AmbiguityCriterion.OBSERVABLE: (("findings", "No security findings in SecurityAuditor output"),),
        AmbiguityCriterion.SCOPED: (("auth_coverage", "auth_coverage empty in SecurityAuditor output"),),
        AmbiguityCriterion.OWNED: (("secrets_audit", "secrets_audit empty in SecurityAuditor output"),),
    },
    "deployer": {
        AmbiguityCriterion.REVERSIBLE_OR_JUSTIFIED: (("rollback_steps", "No rollback_steps in Deployer output"),),
        AmbiguityCriterion.TESTABLE: (("deploy_steps", "No deploy_steps in Deployer output"),),
        AmbiguityCriterion.OBSERVABLE: (("release_notes", "release_notes empty in Deployer output"),),
    },
    "observer": {
        AmbiguityCriterion.MEASURABLE: (("slo_targets", "No SLO targets in Observer output"),),
        AmbiguityCriterion.OBSERVABLE: (
            ("alerts_added", "No alerts in Observer output"),
            ("dashboards_updated", "No dashboards in Observer output"),
        ),
    },
    "refactorer": {
        AmbiguityCriterion.SCOPED: (("items", "No refactor items in Refactorer output"),),
        AmbiguityCriterion.MEASURABLE: (("debt_score_after", "debt_score_after unset in Refactorer output"),),
        AmbiguityCriterion.TESTABLE: (("files_changed", "No files_changed in Refactorer output"),),
    },
}


def _criterion_satisfied(
    output_dict: dict,
    fields: tuple[tuple[str, str], ...],
) -> tuple[bool, str]:
    """Return (passed, detail). Passes if any mapped field is truthy."""
    last_detail = ""
    for field_name, detail in fields:
        value = output_dict.get(field_name)
        # Treat 0 / 0.0 / empty containers as missing — only real evidence passes.
        if value:
            return True, ""
        last_detail = detail
    return False, last_detail


def ambiguity_check(bundle: EvidenceBundle) -> list[dict[str, str]]:
    violations: list[dict[str, str]] = []

    for formula_id, criteria in _CRITERIA_WEIGHTS.items():
        field = _FORMULA_BUNDLE_FIELD.get(formula_id)
        if field is None:
            continue
        output = getattr(bundle, field, None)
        if output is None:
            # Formula not dispatched — skip check
            continue

        output_dict = output.model_dump() if hasattr(output, "model_dump") else {}
        per_formula_map = _CRITERIA_FIELD_MAP.get(formula_id, {})

        for criterion in criteria:
            field_specs = per_formula_map.get(criterion)
            if not field_specs:
                # No mapped fields for this criterion — skip silently rather
                # than raise, so adding a new criterion to _CRITERIA_WEIGHTS
                # without updating the field map remains a soft change.
                continue
            passed, detail = _criterion_satisfied(output_dict, field_specs)
            if not passed:
                violations.append({
                    "formula": formula_id,
                    "criterion": criterion.value,
                    "detail": detail,
                })

    return violations
