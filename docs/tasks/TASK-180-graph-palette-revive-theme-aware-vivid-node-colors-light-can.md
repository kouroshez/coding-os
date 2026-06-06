---
id: TASK-180
title: "Graph palette revive \u2014 theme-aware vivid node colors (light canvas looked lifeless)"
swimlane: core
kind: bug
epic: ui-design-system
labels: [ui, graph, palette, theme-aware, ready]
status: testing
priority: P1
appetite: 1d
created: 2026-06-06
started: 2026-06-05
completed: null
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-180: Graph palette revive — theme-aware vivid node colors (light canvas looked lifeless)

**Outcome (one sentence):** The graph node palette is theme-aware + vivid: a LIGHT palette (deep, saturated — pops on the white canvas) and a DARK palette (bright, saturated — pops on near-black), warmer structure so the canvas reads alive (not the washed mid-grey v2 that looked lifeless in light mode). kindColor(kind, theme) picks the palette (defaults to the live theme-store theme so DOM legends/panels follow); buildGraph bakes the current theme; useSigma re-colors nodes in place on theme toggle (positions preserved); the KINDS legend (filter-bar) + color-legend re-render on toggle. Both palettes ΔE-verified (every common-kind pair distinct). node-colors.test.ts still passes; make ui-build green.

## Read First
- src/core/web/ui/src/lib/node-colors.ts
- src/core/web/ui/src/features/graph/graph-adapter.ts
- src/core/web/ui/src/features/graph/useSigma.ts

## Repro Steps
1. Open the Hub Graph tab in light mode (white canvas).
2. Observe the node cloud.
Expected: vivid, alive node colors that pop on white.
Actual: washed, lifeless, mid-grey-dominated — the v2 palette was tuned for the dark canvas (mid-lightness), so on white it has low contrast and reads dead. User: "what we had before the token changes was better."

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the Graph renders in light mode (white canvas) and again in dark (near-black)
- **When** node-kind dots are painted and the theme is toggled
- **Then** each theme uses its own vivid palette (deep-saturated on white / bright-saturated on dark, warm structure so the canvas is alive), every common-kind pair stays ≥18 ΔE distinct (programmatically verified both palettes), nodes recolor in place on toggle without re-running layout, the KINDS legend follows the theme, node-colors.test.ts still passes, and `make ui-build` is green

## Work Log
