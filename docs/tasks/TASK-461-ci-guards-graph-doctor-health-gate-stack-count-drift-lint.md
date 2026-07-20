---
id: TASK-461
title: "CI guards: graph-doctor health gate + stack-count drift lint"
swimlane: infra
kind: feature
epic: audit-remediation-2026-06
labels: [audit-remediation, ready]
status: archive
priority: P2
appetite: 1d
created: 2026-06-20
started: 2026-06-19
completed: 2026-06-19
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-461: CI guards: graph-doctor health gate + stack-count drift lint

**Outcome (one sentence):** Two silent-rot surfaces get guards: (1) a fast test fails if AGENTS.md or any core rule hardcodes a stack count outside the FS-derived canonical set (the "8 stacks" drift class); (2) a phantom-REGRESSION gate fails when orphaned_phantom graph nodes exceed a baseline ceiling (the 70 cursor-node spike class). A raw healthy:false gate was REJECTED — it is permanently red from benign external-unresolved imports; a per-PR reindex was rejected (minutes, graph DB gitignored) so the graph gate lives in nightly.

## Read First
- .github/workflows/ci.yml
- src/scripts/check_graph_phantoms.py
- tests/test_stack_maturity.py
- docs/engineering/graph-hallucination-cures.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a doc that hardcodes a stack count outside the canonical set, **When** test_stack_maturity runs, **Then** it fails citing file:line and the canonical counts.
**Given** the graph gains orphaned_phantom nodes beyond baseline, **When** check_graph_phantoms.py runs (nightly), **Then** it exits non-zero with the phantom samples.
**Given** the graph-build cost is non-trivial, **When** deciding where to gate, **Then** the chosen approach (nightly full reindex + phantom-regression, NOT per-PR healthy:false) is documented with rationale in the script + workflow.

## Work Log
- 2026-06-20 [claude]: commit 680a07c62f — feat(ci): stack-count drift lint + graph phantom-regression gate (TASK-461)
- 2026-06-20 [claude]: Status transitioned to complete via cos task-done.
- 2026-06-20 [claude]: Shipped stack-count drift lint (test_stack_maturity, 5 tests green) + graph phantom-regression gate…
