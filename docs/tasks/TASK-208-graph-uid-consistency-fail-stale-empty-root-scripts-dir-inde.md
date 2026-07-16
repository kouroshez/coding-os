---
id: TASK-208
title: "graph.uid_consistency FAIL \u2014 stale empty root scripts/ dir indexed as folder:scripts trips legacy-prefix check"
swimlane: "graph_os"
kind: bug
epic: null
labels: [graph, doctor, cleanup, ready]
status: archive
priority: P2
appetite: 1d
created: 2026-06-06
started: 2026-06-05
completed: 2026-06-05
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-208: graph.uid_consistency FAIL — stale empty root scripts/ dir indexed as folder:scripts trips legacy-prefix check

**Outcome (one sentence):** cos doctor graph.uid_consistency returns PASS: the stale empty root scripts/ leftover (from the src/ migration) is removed and its folder:scripts graph node deleted, so the legacy-prefix check finds 0 stale nodes. Reindex no longer recreates it.

## Read First
- src/cli/doctor_extras.py
- src/core/graph_os/

## Repro Steps
1. After the `src/` migration a stale empty root `scripts/` dir remained; the graph indexer registered it as `folder:scripts`.
2. Run `cos doctor` → the `graph.uid_consistency` check.
Expected: PASS (0 stale legacy-prefix nodes).
Actual (pre-fix): FAIL — `folder:scripts` matches a pre-migration legacy-prefix UID and trips the check.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the graph DB + working tree after the `src/` migration
- **When** `cos doctor` runs the `graph.uid_consistency` check (`doctor_extras._check_graph_uid_consistency`)
- **Then** the stale empty root `scripts/` dir is gone, no `folder:scripts` node exists, all LEGACY_PATH_PREFIXES return 0 stale nodes, the check returns PASS, and a reindex cannot recreate `folder:scripts` (no bare root `scripts/` on disk).

## Work Log
- 2026-06-06 [claude]: Done: removed stale empty root scripts/ dir + deleted folder:scripts graph node. cos doctor graph.uid_consistency now PA
- 2026-06-06 [claude]: Status transitioned to complete via cos task-done.
