---
id: TASK-406
title: "Graph tab enterprise UX \u2014 subtree-scoped roots + breadcrumb, adaptive zoom styling, community home, project-name root"
swimlane: "graph_os"
kind: feature
epic: null
labels: [graph-os, hub-ui, ux, ready]
status: archive
priority: P1
appetite: 1d
created: 2026-06-12
started: 2026-06-11
completed: 2026-06-11
agent_session: ses-claude-20260611-002926-83d4
depends_on: []
blocked_by: []
references: []
---
# TASK-406: Graph tab enterprise UX — subtree-scoped roots + breadcrumb, adaptive zoom styling, community home, project-name root

**Outcome (one sentence):** The Graph tab reads like an enterprise tool: clicking a folder/file shows THAT subtree (contains walked downward + semantic edges among members) instead of flooding the whole repo via the parent hop, with an always-visible breadcrumb naming the current root; zoomed-out views stay legible via adaptive styling (position-referenced node sizes + label suppression past a camera-ratio threshold, per Sigma docs and Cambridge Intelligence guidance); and the spine root is labeled with the project name instead of repo-root.

## Read First
- src/core/graph_os/tools/graph.py
- src/core/graph_os/backends/sqlite_backend.py
- src/core/web/ui/src/features/graph/GraphCanvas.tsx
- src/core/web/ui/src/features/graph/useSigma.ts
- src/core/graph_os/extractors/md_links.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** root folder:docs/governance at depth=max, **When** exported with the new subtree scope, **Then** every contains-member is inside the subtree (vs 26-of-8008 today) with semantic edges among members included, and the canvas shows a breadcrumb naming the root path.
- **Given** a 5k-node view, **When** the camera zooms out past the threshold, **Then** node sizes follow graph positions (no fixed-pixel pileup) and labels are suppressed; zooming back in restores detail styling.
- **Given** the spine sidebar, **When** rendered after a reindex, **Then** the root row reads the project name (from the project root directory), not "repo-root".
- **Given** the changes, **When** graph suite + UI vitest + ui-build run, **Then** all green.

## Work Log
- 2026-06-12 [claude]: commit 0f1e709e24 — fix(doctor): system doctor surfaces graph-backend verdict; no expression stubs (TASK-405)
- 2026-06-12 [claude]: Subtree-scoped rooted views shipped: export gained scope=subtree (contains walked downward + backend.edges_among semanti
- 2026-06-12 [claude]: Status transitioned to complete via cos task-done.
- 2026-06-12 [claude]: committed 18bf8f58: src/core/graph_os/backends/sqlite_backend.py, src/core/graph_os/extractors/md_links.py, src/core/gra
