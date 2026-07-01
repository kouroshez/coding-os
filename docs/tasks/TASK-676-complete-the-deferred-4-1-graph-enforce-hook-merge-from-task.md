---
id: TASK-676
title: "Complete the deferred 4\u21921 graph-enforce-hook merge from TASK-577 (graph-gate consolidation)"
swimlane: core
kind: refactor
epic: hook-consolidation
labels: [hooks, graph-gate, consolidation]
status: archive
priority: P2
appetite: 2d
created: 2026-06-30
started: null
completed: null
agent_session: ses-claude-20260628-125542-fc9a
depends_on: [TASK-672]
blocked_by: []
references: []
---
# TASK-676: Complete the deferred 4→1 graph-enforce-hook merge from TASK-577 (graph-gate consolidation)

**Outcome (one sentence):** The deferred 4→1 graph-enforce-hook merge documented in TASK-577 lands: enforce-graph-first-read, enforce-graph-context, enforce-rename-plan, and verify-rename-callers collapse into one ordered graph-gate script (they already share the .graph/ marker namespace and graph_context_match helper), proven behavior-preserving by the F1 (TASK-672) harness.

## Read First
- src/core/hooks/enforce-graph-context.sh
- src/core/hooks/enforce-rename-plan.sh
- src/core/hooks/verify-rename-callers.sh
- src/core/hooks/registry.yaml
- docs/tasks/TASK-577-cluster-4-consolidate-to-one-graph-gate-sh-merge-4-enforce-h.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the F1 parity harness baseline for the four graph hooks, **When** they merge into one ordered graph-gate, **Then** each original hook's exit-code, stderr, and marker writes are preserved.
- **Given** the merged graph-gate, **When** a Write/Edit on core/cli/adapters fires, **Then** graph-context and rename-plan enforcement behave identically (warn and strict modes intact).
- **Given** the consolidation, **When** registry, adapter templates, and goldens regenerate, **Then** verify-hooks and adapter-parity stay green.

## Work Log
