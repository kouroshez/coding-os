---
id: TASK-662
title: "Graduated DoD acceptance gate \u2014 thread task body into evaluate_dod; BLOCK unmet acceptance for risk kinds; fix for_kind model_dump clobber"
swimlane: "board_os"
kind: feature
epic: task-lifecycle-integrity
labels: [dod, gates, abandonment, ready]
status: in_progress
priority: P0
appetite: 2d
created: 2026-06-30
started: 2026-06-30
completed: null
agent_session: ses-claude-20260630-011740-9a32
depends_on: []
blocked_by: []
references: []
---
# TASK-662: Graduated DoD acceptance gate — thread task body into evaluate_dod; BLOCK unmet acceptance for risk kinds; fix for_kind model_dump clobber

**Outcome (one sentence):** evaluate_dod receives the task body and BLOCKs an in_progress→complete transition when Acceptance (G/W/T) is missing or unsatisfied for risk kinds (bug/security/feature) — WARN for chore/docs — closing the DoR-rich/DoD-shallow asymmetry; the new require_acceptance_met DoDKindRules field survives a by_kind override because for_kind merges via model_dump(exclude_unset=True).

## Read First
- src/core/board_os/transition_gates.py
- src/core/board_os/transition_gates_validator.py
- src/core/board_os/transition_gates_cli.py
- src/core/board_os/workflow.py
- docs/governance/task-lifecycle.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a bug-kind task whose Acceptance section is absent or unsatisfied, **When** it transitions to complete, **Then** evaluate_dod returns Verdict.BLOCK with code DOD_ACCEPTANCE_MISSING.
- **Given** a docs-kind task with no acceptance, **When** it completes, **Then** the acceptance check is Verdict.WARN, not BLOCK.
- **Given** a by_kind DoD block that sets require_acceptance_met, **When** for_kind merges it over the default, **Then** the field is preserved (regression test proves the model_dump(exclude_unset=True) fix).
- **Given** an existing task with a satisfied G/W/T acceptance and a fresh verify, **When** it completes, **Then** the gate passes with no new BLOCK (no regression).

## Implementation Guards (verified blast-radius)
- Keep validate_transition's signature stable — thread body INTERNALLY into evaluate_dod (its only prod caller, validator.py:442). 169 downstream nodes break only on a signature change; update the 6 evaluate_dod tests + the complete-path tests in lockstep.
- Config-driven by kind via the existing DoDKindRules.by_kind (mirror DoR's SectionRule) — never a hardcoded kind list in Python.
- Settle first (COMPLICATED → zoom): acceptance-PRESENT is already DoR-enforced at in_progress, so A1's real new value is gating acceptance SATISFIED at complete — choose the mechanism (checkbox convention vs verify/work-log evidence) before coding, else the gate is a no-op.

## Work Log
