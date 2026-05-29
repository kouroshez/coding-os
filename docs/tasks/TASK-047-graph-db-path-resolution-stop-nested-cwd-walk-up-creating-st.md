---
id: TASK-047
title: "graph DB-path resolution: stop nested-cwd walk-up creating stray .coding-os DBs (defeats TASK-117)"
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

# TASK-047: graph DB-path resolution: stop nested-cwd walk-up creating stray .coding-os DBs (defeats TASK-117)

**Outcome (one sentence):** resolve_db_path/_find_project_root_from_cwd stop anchoring on a stray nested .coding-os when invoked from a subdir — walk up to the registered project root. Prevents the 3 stray partial-index DBs (3780/2281/0 nodes) created by subdir invocations. Cleanup: user removes existing strays (rm docs/.coding-os src/cli/.coding-os src/core/thinking_os/.coding-os). Evidence: audit-graph-live-round5-2026-05-29.md.

## Read First
- docs/tasks/audits/audit-graph-live-round5-2026-05-29.md
- src/core/thinking_os/database.py

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
- 2026-05-29 [claude]: DONE — resolve_db_path prefers marker-co-located root, skips stray nested .coding-os; verified live (src/cli, docs, thin
