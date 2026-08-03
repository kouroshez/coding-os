---
id: TASK-779
title: "Bump angular scaffold to current stable (v18 \u2192 v20+) with migration + runtime verify"
swimlane: core
kind: chore
epic: null
labels: [ready]
status: archive
priority: P2
appetite: 1d
created: 2026-07-04
started: 2026-07-04
completed: 2026-07-04
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-779: Bump angular scaffold to current stable (v18 → v20+) with migration + runtime verify

**Outcome (one sentence):** The angular seed pins the current stable Angular (v18 is two majors behind; confirm exact latest via firecrawl at implementation), scaffold code + SKILL/anatomy idioms updated for any breaking changes, verified by an actual ng build/test run — not a blind pin bump.

## Work Log
- 2026-07-04 [claude]: Migrated angular scaffold v18->v22 (current stable, verified via real npm registry). Adopted @angular/build builders,…
