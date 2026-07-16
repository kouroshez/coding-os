---
id: TASK-408
title: "Graph root node distinct focal style \u2014 reserved brand-logomark color + home glyph + legend entry"
swimlane: "graph_os"
kind: feature
epic: null
labels: [graph-os, hub-ui, ux, design, ready]
status: archive
priority: P2
appetite: 1d
created: 2026-06-12
started: 2026-06-11
completed: 2026-06-11
agent_session: ses-claude-20260611-002926-83d4
depends_on: []
blocked_by: []
references: []
---
# TASK-408: Graph root node distinct focal style — reserved brand-logomark color + home glyph + legend entry

**Outcome (one sentence):** The repo-root anchor node on the Hub Graph canvas is visually unmistakable as "the project itself", not just another amber folder. It wears a RESERVED focal style outside the categorical kind palette — the brand-logomark iris weight (#4F46E5, the same indigo the Coding OS wordmark uses), a dedicated home+halo glyph (not the generic folder icon), the existing dominant size and always-on caption — and the Legend documents it as a distinct "project root" entry. Theme toggle preserves the reserved color (does not recolor it as a folder).

## Read First
- src/core/web/ui/src/lib/node-colors.ts
- src/core/web/ui/src/features/graph/graph-adapter.ts
- src/core/web/ui/src/features/graph/useSigma.ts
- docs/engineering/design-system.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the Hub Graph tab rendered over the coding-os repo (root uid `folder:.`), where the root previously shared the amber folder color `#E8A24A` and folder glyph with every other directory
- **When** the canvas builds the graph (overview or rooted) and the user toggles dark/light theme
- **Then** the root node renders in the reserved brand-logomark iris `#4F46E5` (a color used by no NodeKind), carries a dedicated home+halo glyph instead of the folder icon, keeps its dominant size + persistent caption, stays that reserved color across a theme toggle (not recolored as a folder), and the Legend shows a leading "project root" swatch — verified by vitest + a live Hub probe of `/api/graph/export` root attrs and a clean `make ui-build`.

## Work Log
- 2026-06-12 [claude]: Root anchor now wears reserved focal style: iris-600 #4F46E5 (logomark weight, absent from all 24 kind colors) + home-in
- 2026-06-12 [claude]: committed e4f790d2: docs/engineering/design-system.md, src/core/web/ui/src/features/graph/color-legend.tsx, src/core/web
