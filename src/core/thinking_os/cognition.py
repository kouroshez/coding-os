"""Coding OS — Formula-agent supervisor."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from _cognition_registry import (
    AGENTS_DIR as AGENTS_DIR,
    SITUATIONS_DIR as SITUATIONS_DIR,
    load_agent_registry as load_agent_registry,
    load_situation_registry as load_situation_registry,
)
from cognition_schemas import (
    EvidenceBundle,
    NextAction,
    SupervisorState,
)

logger = logging.getLogger("coding_os.cognition")

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
    parallel_available = [f for f in parallel if f not in state.dispatched and f in remaining]
    if parallel_available:
        all_parallel = [formula_id, *parallel_available]
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

    Priority (composer chain):
      1. If state.pending already set by caller → use as-is.
      2. If persona_id starts with "chain:" → that chain.
      3. Empty list.
    """
    if state.pending:
        return list(state.pending)

    # Caller passed a composer-derived role chain as persona_id?
    # Format: "chain:analyst,architect,implementer,reviewer" (role-chain persona format)
    if state.persona_id.startswith("chain:"):
        return [r.strip() for r in state.persona_id[6:].split(",") if r.strip()]

    return []
