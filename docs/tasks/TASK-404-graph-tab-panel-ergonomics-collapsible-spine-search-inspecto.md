---
id: TASK-404
title: "Graph tab panel ergonomics \u2014 collapsible spine/search/inspector + URL-synced root selection"
swimlane: "graph_os"
kind: feature
epic: null
labels: [graph-os, hub-ui, ux, ready]
status: archive
priority: P2
appetite: 4h
created: 2026-06-12
started: 2026-06-11
completed: 2026-06-11
agent_session: ses-claude-20260611-002926-83d4
depends_on: []
blocked_by: []
references: []
---
# TASK-404: Graph tab panel ergonomics — collapsible spine/search/inspector + URL-synced root selection

**Outcome (one sentence):** Graph tab panels get out of the way: the Contains-spine sidebar, the Search/Kinds/Edges filter panel, and the app-shell Inspector each collapse behind a toggle so the canvas can use the full viewport; selecting a root from the tree updates the URL (/graph/:rootUid) so refresh/share keeps the selection, honoring the SPA's URL-source-of-truth rule.

## Read First
- src/core/web/ui/src/pages/GraphPage.tsx
- src/core/web/ui/src/features/graph/ContainsTree.tsx
- src/core/web/ui/src/features/graph/filter-bar.tsx
- src/core/web/ui/src/layout/AppShell.tsx
- src/core/web/ui/src/layout/Inspector.tsx

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the Graph tab, **When** the user toggles the spine sidebar, the filter panel, or the inspector, **Then** the panel collapses to a slim affordance and the canvas reclaims the space; state persists while navigating within the session.
- **Given** a root picked from the Contains-spine tree, **When** the page is refreshed, **Then** the same root is selected because the click navigated to /graph/:rootUid (URL is the source of truth; Clear returns to /graph).
- **Given** the changes, **When** `make ui-build` and the UI test suite run, **Then** both pass.

## Work Log
- 2026-06-12 [claude]: Edit graph-store.ts
- 2026-06-12 [claude]: Edit graph-store.ts
- 2026-06-12 [claude]: Edit graph-store.ts
- 2026-06-12 [claude]: Edit GraphPage.tsx
- 2026-06-12 [claude]: Edit GraphPage.tsx
- 2026-06-12 [claude]: Edit GraphPage.tsx
- 2026-06-12 [claude]: Edit AppShell.tsx
- 2026-06-12 [claude]: Edit AppShell.tsx
- 2026-06-12 [claude]: Edit AppShell.tsx
- 2026-06-12 [claude]: Edit ContainsTree.tsx
- 2026-06-12 [claude]: Edit ContainsTree.tsx
- 2026-06-12 [claude]: Edit ContainsTree.tsx
- 2026-06-12 [claude]: Edit ContainsTree.tsx
- 2026-06-12 [claude]: Panels now collapse: spine sidebar (PanelLeftClose in header ↔ 28px rail), Search/Kinds/Edges filter card (X ↔ sliders i
- 2026-06-12 [claude]: Status transitioned to complete via cos task-done.
- 2026-06-12 [claude]: committed eafd3004: src/core/web/ui/src/features/graph/ContainsTree.tsx, src/core/web/ui/src/layout/AppShell.tsx, src/co
