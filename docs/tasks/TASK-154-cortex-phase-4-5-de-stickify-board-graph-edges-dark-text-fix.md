---
id: TASK-154
title: "Cortex Phase 4+5 — de-stickify board, graph edges, dark-text fixes, a11y motion"
swimlane: core
kind: refactor
epic: ui-design-system
labels: [ui, design-system, board, graph, a11y, ready]
status: archive
priority: P1
appetite: "1d"
created: 2026-06-05
started: 2026-06-05
completed: 2026-06-05
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-154: Cortex Phase 4+5 — de-stickify board, graph edges, dark-text fixes, a11y motion

**Outcome (one sentence):** Kill the remaining sticky-note aesthetic + dark-mode color bugs surfaced by grep: board task-cards drop the cursive Kalam/Caveat handwriting font + random tilt (stableRotation) + hardcoded near-black text (#1a1814 → invisible on the new dark tints) in favor of inherited Inter + var(--cos-text) + flat 8px radius; the Sigma graph EDGE_PALETTE and hover/search highlight colors are harmonized onto the new node hue families (steel/Iris/azure/teal/violet), removing leftover brown (#8B5A2B) and old-orange (#D96C2C/#f97316) edges; a global prefers-reduced-motion block is added (a11y). make ui-build green, zero new deps.

## Read First
- src/core/web/ui/src/features/cos-board/CosBoardPage.tsx
- src/core/web/ui/src/features/graph/graph-adapter.ts
- src/core/web/ui/src/features/graph/useSigma.ts
- docs/engineering/design-system.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the board and graph render in dark mode (default)
- **When** task-cards and graph edges paint, and a user with reduced-motion preference loads the app
- **Then** task-card text is legible (var(--cos-text), not hardcoded near-black), cards use inherited Inter + flat radius + no tilt, every graph edge color belongs to the new harmonized node-hue families (no brown/old-orange leftovers), and non-essential animation is disabled under `prefers-reduced-motion`; `make ui-build` is green with zero new deps

Spec SSOT: [docs/engineering/design-system.md](../engineering/design-system.md)

## Work Log
- 2026-06-05 [claude]: Phase 4+5 shipped (commit de5687c): board task-cards de-stickified (removed cursive Kalam font, stableRotation tilt fn, 
