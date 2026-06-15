---
id: TASK-407
title: "Graph home as community map \u2014 focus+context default view (design + implementation)"
swimlane: "graph_os"
kind: feature
epic: null
labels: [graph-os, hub-ui, ux, design, ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-12
started: 2026-06-14
completed: 2026-06-14
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-407: Graph home as community map — focus+context default view (design + implementation)

**Outcome (one sentence):** The Graph tab's no-root home renders an InfraNodus/Bloom-style community map: Louvain communities as labeled colored groups with their top hubs, non-focus nodes de-emphasized (gray), giving the canvas a recognizable architecture-map identity instead of a random-feeling blend sample; built on the existing processes-mode data after a render-quality design pass (the blind default-switch was rejected during TASK-406 because only 2 community nodes surfaced at a 500-node budget).

## Read First
- src/core/graph_os/tools/graph.py (processes-mode export + node-budget allocation)
- src/core/graph_os/communities.py (Louvain community detection)
- src/core/graph_os/tests/test_smart_export.py (TestProcessesMode — the regression fixture to extend)
- src/core/web/ui/src/features/graph/GraphCanvas.tsx
- src/core/web/ui/src/features/graph/graph-adapter.ts (buildGraph)
- src/core/web/ui/src/lib/node-colors.ts (community color + normalization)

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a backend with >=6 detectable Louvain communities (a stub fixture mirroring TestProcessesMode in src/core/graph_os/tests/test_smart_export.py), **When** the processes-mode export runs at max_nodes=500, **Then** the response contains AT LEAST 6 distinct community-kind nodes — directly guarding the TASK-406 regression where only 2 surfaced.
- **Given** the same backend where the top community alone holds 400+ members, **When** the processes export allocates the node budget, **Then** members-per-community are capped (top hubs only) so budget is reserved across communities — a new test asserts no single community consumes more than its fair share and every community above min_size appears at least as its header node.
- **Given** the no-root home view, **When** the export resolves in processes mode with no selected root, **Then** GraphCanvas / graph-adapter render each community node with its label forced on (group color from node-colors.ts) and de-emphasize non-hub member nodes (reduced size / muted color) — a vitest case asserts community nodes get forceLabel and member nodes do not.
- **Given** this is a design+implementation task, **When** the work lands, **Then** a design-pass note (a section in docs/engineering/hub-architecture.md or a new doc under docs/engineering/) records the community-home layout, the per-community budget-reservation rule, and the de-emphasis styling, and `make docs-lint` is green.
- **Given** the backend changes, **When** `uv run --extra graph_os pytest src/core/graph_os/tests/test_smart_export.py src/core/graph_os/tests/test_communities.py -q` runs, **Then** all green (including the new >=6-community and budget-reservation assertions).
- **Given** the UI changes, **When** `npm run test` and `npm run build` run inside src/core/web/ui/, **Then** both pass (vitest green; tsc + vite build succeed).

## Rollback
Revert the graph.py budget-allocation change and the GraphCanvas / graph-adapter render changes (the no-root home falls back to the prior blend-sample view) and delete the design-pass note; pure view/export behavior, no schema or persisted-state change.

## Work Log
- 2026-06-15 [claude]: committed 34040af9: docs/engineering/00-index.md, docs/engineering/hub-architecture.md, src/core/graph_os/tests/test_sma
