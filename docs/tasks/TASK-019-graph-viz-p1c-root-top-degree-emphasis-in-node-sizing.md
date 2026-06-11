---
id: TASK-019
title: "graph viz P1c: root + top-degree emphasis in node sizing"
swimlane: core
kind: feature
epic: null
labels: [graph-viz, ui]
status: complete
priority: P1
appetite: "1h"
created: 2026-05-23
started: 2026-05-23
completed: 2026-05-23
agent_session: ses-claude-20260523-010526-e647
depends_on: []
blocked_by: []
references:
  - src/core/web/ui/src/features/graph/graph-adapter.ts
---
# TASK-019: graph viz P1c — root + top-degree emphasis

**Outcome (one sentence):** The repo-root folder node ( `.` ) is the visually-largest node on the canvas, and the top-N highest-degree nodes always carry a label — so the viewer's eye snaps to the centre of importance instead of getting lost in the cloud.

## Read First
- [src/core/web/ui/src/features/graph/graph-adapter.ts](../../src/core/web/ui/src/features/graph/graph-adapter.ts) — `sizeFor()` and `labelForceFor()` (lines 90-100)

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the graph canvas renders with depth=`all` on the meta-repo
- **When** the user opens the Graph tab
- **Then** the repo-root folder node has the maximum node radius (`size=28+`), carries `forceLabel=true`, and visually dominates the canvas; the next-tier structural anchors (top-level folders, MCP-tool hubs, route entry-points) are at least 1.5× the median node size; `npm run build` clean.

## Work Log
- 2026-05-23 — confirmed repo-root uid = `folder:.` via `sqlite3 SELECT … WHERE kind='folder'`; patched `graph-adapter.ts` `sizeFor()`/`labelForceFor()` with three additive boosts: `ROOT_UIDS` (γ·root_bonus → size=32, forceLabel=true), top-5 by degree (×1.4 hubBoost + forceLabel), existing log-degree formula preserved as the base. `npm run build` → 1.74s, no TS errors.
- 2026-05-23 [claude]: Status transitioned to complete via cos task-done.
