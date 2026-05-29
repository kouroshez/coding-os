---
id: TASK-046
title: "graph quality tuning: doctor orphan relabel + centrality contains-filter + communities/ranking de-test"
swimlane: infra
kind: refactor
epic: null
labels: []
status: icebox
priority: P3
appetite: "1d"
created: 2026-05-29
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-046: graph quality tuning: doctor orphan relabel + centrality contains-filter + communities/ranking de-test

**Outcome (one sentence):** Usefulness fixes: (1) cos_graph_doctor buckets orphans by uid prefix (467/905 mislabeled orphaned_external_unresolved); (2) centrality(degree) default-excludes 'contains' edges so code chokepoints surface; (3) communities/ranking down-rank test_*-dominated clusters so production subsystems are visible (folds F6/TASK-040). Evidence: audit-graph-live-round5-2026-05-29.md.

## Read First
- docs/tasks/audits/audit-graph-live-round5-2026-05-29.md
- src/core/graph_os/tools/graph.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** ...
- **When** ...
- **Then** ...

## Work Log
- 2026-05-29 [claude]: DEFERRED (deliberate, not rushed) — all 3 sub-fixes (doctor orphan re-bucket, centrality contains-exclusion, communities
