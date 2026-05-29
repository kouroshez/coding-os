---
id: TASK-044
title: "graph entrypoints + sample_nodes: drop test-conflation + representative sampling"
swimlane: infra
kind: bug
epic: null
labels: []
status: icebox
priority: P2
appetite: "1d"
created: 2026-05-29
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-044: graph entrypoints + sample_nodes: drop test-conflation + representative sampling

**Outcome (one sentence):** cos_graph_entrypoints stops ranking test_* functions (76% of total_count=4671 at 0.85 > real CLI root 0.6) as entry points; sample_nodes draws a representative sample (not ORDER BY id ASC fixed-prefix) so similar/entrypoints see the whole kind population. Shared sampler — verify communities + determinism tests. Evidence: audit-graph-live-round5-2026-05-29.md.

## Read First
- docs/tasks/audits/audit-graph-live-round5-2026-05-29.md
- src/core/graph_os/entry_points.py

## Repro Steps
1. (fill in: exact steps to reproduce)
2. ...
Expected: ...
Actual: ...

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** ...
- **When** ...
- **Then** ...

## Work Log
- 2026-05-29 [claude]: DONE — entrypoints excludes kind=test by default (was 76% of results); total_count 4671→1093, real cli/main now top-rank
