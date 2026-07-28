---
id: TASK-642
title: "Add an autonomous repairer role/formula: budget-capped repair loop with verify-suite exit code as fitness"
swimlane: core
kind: feature
epic: multi-model-autonomy
labels: [autonomy, repair, dispatch, ready]
status: archive
priority: P2
appetite: 1d
created: 2026-06-28
started: 2026-06-28
completed: 2026-06-28
agent_session: ses-system-auto-archive
depends_on: [TASK-639]
blocked_by: []
references: []
---
# TASK-642: Add an autonomous repairer role/formula: budget-capped repair loop with verify-suite exit code as fitness

**Outcome (one sentence):** A capability-restricted, budget-capped `repairer` role dispatched in-process via the existing SDK dispatcher, whose objective fitness is the matrix verify-suite exit code; triggered from cos_graph_test_gap findings. Reuses sdk_dispatcher + budget.py + verify-suites.yaml — no standalone binary, no new subprocess, no re-spawned claude grandchild.

## Read First
- src/core/thinking_os/roles/reviewer.yaml
- src/adapters/claude/sdk_dispatcher.py
- src/core/thinking_os/tools/cognition.py
- docs/adapters/claude-sdk.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a failing matrix verify-suite, **When** the repairer role is dispatched, **Then** it iterates (capability-restricted tools, budget-capped) until the suite exits 0 or the budget/attempt cap is hit.
- **Given** a suite already green, **When** invoked, **Then** it refuses (no-op) instead of churning.
- **Given** the repair loop spawns, **When** it runs, **Then** it reuses the in-process ClaudeSDKDispatcher (not a re-spawned claude subprocess) and records cost to formula_dispatches.
- **Given** the adapters and thinking_os suites, **When** run, **Then** green.

## Work Log
- 2026-06-28 [claude]: Edit repair.py
- 2026-06-28 [claude]: Edit test_repair.py
- 2026-06-28 [claude]: Edit repairer.md
- 2026-06-28 [claude]: Edit test_cognition_supervisor.py
- 2026-06-28 [claude]: Shipped the autonomous repair core minimally + flag-gated. repair.py: repair_loop (COS_REPAIRER) injects the…
- 2026-06-28 [claude]: Status transitioned to complete via cos task-done.
