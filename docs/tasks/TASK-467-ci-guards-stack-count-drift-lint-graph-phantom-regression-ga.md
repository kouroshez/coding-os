---
id: TASK-467
title: "CI guards: stack-count drift lint + graph phantom-regression gate"
swimlane: infra
kind: feature
epic: audit-remediation-2026-06
labels: [audit-remediation, ci, ready]
status: archive
priority: P2
appetite: 1d
created: 2026-06-20
started: null
completed: null
agent_session: ses-claude-20260619-211916-fd8f
depends_on: []
blocked_by: []
references: []
---
# TASK-467: CI guards: stack-count drift lint + graph phantom-regression gate

**Outcome (one sentence):** Two silent-rot surfaces get guards: (1) a fast test fails if AGENTS.md or any core rule hardcodes a stack count outside the FS-derived canonical set (the "8 stacks" drift class); (2) a phantom-REGRESSION gate (check_graph_phantoms.py + make target + nightly CI reindex step) fails when orphaned_phantom graph nodes exceed a baseline ceiling — the real "graph rotted" signal (the 70 cursor-node spike). A raw healthy:false gate was rejected (permanently red from benign external-unresolved imports); a per-PR reindex was rejected (minutes, graph DB gitignored) so the graph gate lives in nightly.

## Read First
- .github/workflows/ci.yml
- src/scripts/check_graph_phantoms.py
- tests/test_stack_maturity.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a doc that hardcodes a stack count outside the canonical set, **When** test_stack_maturity runs, **Then** it fails citing file:line and the canonical counts.
**Given** the graph gains orphaned_phantom nodes beyond baseline, **When** check_graph_phantoms.py runs (nightly), **Then** it exits non-zero with the phantom samples.
**Given** the graph-build cost, **When** deciding where to gate, **Then** the chosen approach (nightly full reindex + phantom-regression, NOT per-PR healthy:false) is documented with rationale in the script + workflow.

## Work Log
