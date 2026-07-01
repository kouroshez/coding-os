---
id: TASK-672
title: "Behavior-parity harness for hook merges + delete the low-value warn-template-drift hook"
swimlane: core
kind: refactor
epic: hook-consolidation
labels: [hooks, harness, parity, ready]
status: complete
priority: P1
appetite: 2d
created: 2026-06-30
started: 2026-06-30
completed: 2026-06-30
agent_session: ses-claude-20260630-221108-17bf
depends_on: []
blocked_by: []
references: []
---
# TASK-672: Behavior-parity harness for hook merges + delete the low-value warn-template-drift hook

**Outcome (one sentence):** A behavior-parity harness captures each hook's (event, input) to (exit-code, stderr, additionalContext) signature as a golden baseline so a hook MERGE can be proven behavior-preserving before and after, and the low-value warn-template-drift hook is deleted with registry + adapter-template + golden regen as the first harness-guarded change — this is the prerequisite that de-risks F2 and F3.

## Read First
- src/core/hooks/registry.yaml
- src/core/hooks/warn-template-drift.sh
- tests/test_adapters.py
- tests/test_adapter_parity.py
- docs/playbooks/hook-authoring.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a set of hooks, **When** the parity harness runs, **Then** it records each hook's exit-code, stderr, and additionalContext for representative inputs as a golden baseline.
- **Given** warn-template-drift removed, **When** registry, adapter-templates, and goldens are regenerated, **Then** verify-hooks and adapter-parity stay green and no consumer references a dangling hook.
- **Given** a future merge, **When** the harness re-runs, **Then** any behavior divergence fails the test — the de-risking contract F2 and F3 depend on.

## Work Log
- 2026-07-01 [claude]: Built test_hook_parity.py (deterministic golden: 4 no-op + 2 block cases, catches signature divergence). Deleted…
- 2026-07-01 [claude]: Status transitioned to complete via cos task-done.
