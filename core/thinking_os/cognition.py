"""
Coding OS — Formula-agent supervisor (Phase M).

PURPOSE:      Pure-Python state machine that decides what to dispatch next.
              Never spawns subagents — only returns NextAction for the main agent.
INPUT:        SupervisorState + loaded persona/situation registries.
OUTPUT:       NextAction (dispatch / backtrack / done).
DEPENDENCIES: cognition_schemas, PyYAML, pathlib; no DB, no MCP.
NOTES:        Deterministic and recursion-free. Formula-agents MUST NOT call
              cos_supervise — only the main agent does.
"""

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
    """
    PURPOSE:      Return all situational dispatch chains keyed by situation_id.
    INPUT:        situations/registry.yaml on disk.
    OUTPUT:       {situation_id: situation_dict}
    DEPENDENCIES: PyYAML, SITUATIONS_DIR.
    """
    global _situation_registry
    if _situation_registry is None:
        reg = _load_yaml(SITUATIONS_DIR / "registry.yaml")
        _situation_registry = {s["id"]: s for s in reg.get("situations", [])}
    return _situation_registry


def load_agent_registry() -> dict[str, dict[str, Any]]:
    """
    PURPOSE:      Parse frontmatter from each F<N>_<name>.md agent file.
    INPUT:        agents/ directory.
    OUTPUT:       {formula_id: frontmatter_dict}  e.g. {"F2": {...}}
    DEPENDENCIES: PyYAML, AGENTS_DIR.
    NOTES:        Frontmatter delimited by '---' lines.
    """
    global _agent_registry
    if _agent_registry is not None:
        return _agent_registry
    registry: dict[str, dict[str, Any]] = {}
    for agent_file in sorted(AGENTS_DIR.glob("F*.md")):
        text = agent_file.read_text()
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 3:
                meta = yaml.safe_load(parts[1]) or {}
                fid = meta.get("id", agent_file.stem.split("_")[0])
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
    "F1": "F1_research",
    "F2": "F2_decompose",
    "F3": "F3_architect",
    "F4": "F4_document",
    "F5": "F5_implement",
    "F6": "F6_test_review",
    "F7": "F7_debug",
    "F8": "F8_security",
    "F9": "F9_deploy",
    "F10": "F10_monitor",
    "F11": "F11_refactor",
}


def build_input_slice(formula_id: str, bundle: EvidenceBundle) -> dict[str, Any]:
    """
    PURPOSE:      Extract only the bundle fields a formula needs as its input.
    INPUT:        Formula id + current EvidenceBundle.
    OUTPUT:       dict matching F<N>Input (upstream outputs only; no future formulas).
    NOTES:        F3 sees F1+F2; F5 sees F2+F3; etc.
    """
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
    """
    PURPOSE:      Return the next action the main agent should take.
    INPUT:        Current supervisor state + evidence bundle.
    OUTPUT:       NextAction — one of: classify | dispatch | dispatch_parallel |
                  backtrack | done.
    DEPENDENCIES: cognition_schemas, persona/situation registries.
    NOTES:        Deterministic. Never spawns agents. Called repeatedly until
                  action == "done".
    """
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
    agent_file = meta.get("_file", f"F{formula_id[1:]}.md")

    slice_data = build_input_slice(formula_id, bundle)

    # Check for parallelisable formulas (F8 layers)
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
        agent_file=f"core/thinking_os/agents/{agent_file}",
        reason=f"Next in chain: {formula_id}",
    )


def _build_queue(state: SupervisorState) -> list[str]:
    """
    Build the ordered dispatch queue.

    Priority (Phase N — Phase M personas removed in v0.3):
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
    # Format: "chain:F2,F3,F5,F6" (supported by task-start.sh)
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
    """
    PURPOSE:      Re-queue a formula for re-dispatch (backtrack path).
    INPUT:        Current state, formula that triggered backtrack, target formula.
    OUTPUT:       NextAction with action=backtrack.
    NOTES:        Anti-Paralysis: ≥3 backtracks → advisory; ≥5 → stronger warning.
    """
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
    "F1": [
        AmbiguityCriterion.OBSERVABLE,
        AmbiguityCriterion.SCOPED,
    ],
    "F2": [
        AmbiguityCriterion.SCOPED,
        AmbiguityCriterion.OWNED,
        AmbiguityCriterion.OBSERVABLE,
        AmbiguityCriterion.TESTABLE,
    ],
    "F3": [
        AmbiguityCriterion.SCOPED,
        AmbiguityCriterion.MEASURABLE,
        AmbiguityCriterion.REVERSIBLE_OR_JUSTIFIED,
    ],
    "F4": [
        AmbiguityCriterion.OBSERVABLE,
        AmbiguityCriterion.SCOPED,
    ],
    "F5": [
        AmbiguityCriterion.TESTABLE,
        AmbiguityCriterion.SCOPED,
        AmbiguityCriterion.OWNED,
    ],
    "F6": [
        AmbiguityCriterion.MEASURABLE,
        AmbiguityCriterion.TESTABLE,
    ],
    "F7": [
        AmbiguityCriterion.OBSERVABLE,
        AmbiguityCriterion.TESTABLE,
        AmbiguityCriterion.SCOPED,
    ],
    "F8": [
        AmbiguityCriterion.OBSERVABLE,
        AmbiguityCriterion.SCOPED,
        AmbiguityCriterion.OWNED,
    ],
    "F9": [
        AmbiguityCriterion.REVERSIBLE_OR_JUSTIFIED,
        AmbiguityCriterion.TESTABLE,
        AmbiguityCriterion.OBSERVABLE,
    ],
    "F10": [
        AmbiguityCriterion.MEASURABLE,
        AmbiguityCriterion.OBSERVABLE,
    ],
    "F11": [
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
    "F1": {
        AmbiguityCriterion.OBSERVABLE: (("sources", "No sources cited in F1 research"),),
        AmbiguityCriterion.SCOPED: (
            ("key_findings", "No key_findings recorded in F1"),
            ("recommended_next", "recommended_next is empty in F1"),
        ),
    },
    "F2": {
        AmbiguityCriterion.SCOPED: (("scope_in", "scope_in is empty in F2 output"),),
        AmbiguityCriterion.OWNED: (("actors", "No actors defined in F2 output"),),
        AmbiguityCriterion.OBSERVABLE: (("success_metrics", "No success_metrics in F2 output"),),
        AmbiguityCriterion.TESTABLE: (("scenarios", "No scenarios defined in F2 output"),),
    },
    "F3": {
        AmbiguityCriterion.SCOPED: (("selected_style", "selected_style empty in F3 output"),),
        AmbiguityCriterion.MEASURABLE: (("nfr_targets", "No NFR targets recorded in F3"),),
        AmbiguityCriterion.REVERSIBLE_OR_JUSTIFIED: (("adrs", "No ADRs recorded in F3"),),
    },
    "F4": {
        AmbiguityCriterion.OBSERVABLE: (
            ("docs_created", "No docs_created in F4"),
            ("docs_updated", "No docs_updated in F4"),
        ),
        AmbiguityCriterion.SCOPED: (("changelog_entry", "changelog_entry empty in F4"),),
    },
    "F5": {
        AmbiguityCriterion.TESTABLE: (
            ("files_created", "No files_created in F5"),
            ("files_modified", "No files_modified in F5"),
        ),
        AmbiguityCriterion.SCOPED: (("implementation_notes", "implementation_notes empty in F5"),),
        AmbiguityCriterion.OWNED: (("open_items", "open_items unset (None) in F5"),),
    },
    "F6": {
        AmbiguityCriterion.MEASURABLE: (("coverage_summary", "No coverage_summary in F6"),),
        AmbiguityCriterion.TESTABLE: (("test_cases", "No test_cases in F6"),),
    },
    "F7": {
        AmbiguityCriterion.OBSERVABLE: (("root_cause", "root_cause empty in F7"),),
        AmbiguityCriterion.TESTABLE: (("regression_tests_added", "No regression tests in F7"),),
        AmbiguityCriterion.SCOPED: (("fix_applied", "fix_applied empty in F7"),),
    },
    "F8": {
        AmbiguityCriterion.OBSERVABLE: (("findings", "No security findings in F8"),),
        AmbiguityCriterion.SCOPED: (("auth_coverage", "auth_coverage empty in F8"),),
        AmbiguityCriterion.OWNED: (("secrets_audit", "secrets_audit empty in F8"),),
    },
    "F9": {
        AmbiguityCriterion.REVERSIBLE_OR_JUSTIFIED: (("rollback_steps", "No rollback_steps in F9"),),
        AmbiguityCriterion.TESTABLE: (("deploy_steps", "No deploy_steps in F9"),),
        AmbiguityCriterion.OBSERVABLE: (("release_notes", "release_notes empty in F9"),),
    },
    "F10": {
        AmbiguityCriterion.MEASURABLE: (("slo_targets", "No SLO targets in F10"),),
        AmbiguityCriterion.OBSERVABLE: (
            ("alerts_added", "No alerts in F10"),
            ("dashboards_updated", "No dashboards in F10"),
        ),
    },
    "F11": {
        AmbiguityCriterion.SCOPED: (("items", "No refactor items in F11"),),
        AmbiguityCriterion.MEASURABLE: (("debt_score_after", "debt_score_after unset in F11"),),
        AmbiguityCriterion.TESTABLE: (("files_changed", "No files_changed in F11"),),
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
    """
    PURPOSE:      Verify bundle satisfies per-formula ambiguity criteria.
    INPUT:        EvidenceBundle after formula dispatch.
    OUTPUT:       List of violation dicts {formula, criterion, detail}.
    NOTES:        Empty list = gate passes. Called once at PLAN→EXECUTE.
                  Formulas without dispatched output are skipped — gate
                  fires only over evidence the agent already produced.
    """
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
