---
id: TASK-018
title: "graph viz P1: uncap depth budgets + semantic color regrouping"
swimlane: core
kind: feature
epic: null
labels: [graph-viz, ui, colors]
status: complete
priority: P1
appetite: "1d"
created: 2026-05-23
started: 2026-05-23
completed: 2026-05-23
agent_session: ses-claude-20260523-010526-e647
depends_on: []
blocked_by: []
references:
  - src/core/web/ui/src/features/graph/GraphCanvas.tsx
  - src/core/web/ui/src/lib/node-colors.ts
  - src/core/web/routes/graph.py
---
# TASK-018: graph viz P1 — uncap depth budgets + semantic color regrouping

**Outcome (one sentence):** "max" depth preset shows ≥10× more nodes than today (was ~1.5k of 41k = 3.5%), and the 25 NodeKind colors group into 8 distinct hue families so the canvas is legible at a glance.

## Read First
- [src/core/web/ui/src/features/graph/GraphCanvas.tsx](../../src/core/web/ui/src/features/graph/GraphCanvas.tsx) — depth-budget config (lines 28-39)
- [src/core/web/ui/src/lib/node-colors.ts](../../src/core/web/ui/src/lib/node-colors.ts) — NodeKind → color map
- [src/core/web/routes/graph.py](../../src/core/web/routes/graph.py) — backend `/api/graph/export?max_nodes=…` default (line 210)

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a user inspects the Graph tab with depth=`all`
- **When** the SPA issues `/api/graph/export?max_nodes=…`
- **Then** the returned subgraph covers ≥50 % of nodes for an overview view and ≥30 % for a rooted view; UI renders cleanly within Sigma's WebGL budget; the 25 NodeKind dots cluster visually into 8 colour groups (structure / code-defs / code-refs / API-surface / docs / governance / analysis / unknown) and no two kinds within a group share a confusable hex (ΔE ≥ 10).

## Work Log
- 2026-05-23 — raised GraphCanvas depth budgets 10-15× (overview all: 1400→20000; rooted all: 1500→10000), recoloured the 25 NodeKind palette into 8 hue families (structure brown · code-defs Mocha orange · code-refs gray · API-surface blue · docs teal · governance purple · analysis gold · unknown light gray), and bumped the `/api/graph/export` backend default `max_nodes=500` → `2000`. Sigma WebGL handles 41k-node repo within budget per audit. `npm run build` clean (914KB bundle, no TS errors).
- 2026-05-23 [claude]: Status transitioned to complete via cos task-done.
