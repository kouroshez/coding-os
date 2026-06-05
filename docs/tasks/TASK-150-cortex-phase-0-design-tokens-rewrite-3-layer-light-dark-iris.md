---
id: TASK-150
title: "Cortex Phase 0 — design tokens rewrite (3-layer, light+dark, Iris)"
swimlane: core
kind: refactor
epic: ui-design-system
labels: [ui, design-system, tokens, css, ready]
status: testing
priority: P1
appetite: "1d"
created: 2026-06-05
started: 2026-06-05
completed: null
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-150: Cortex Phase 0 — design tokens rewrite (3-layer, light+dark, Iris)

**Outcome (one sentence):** Rewrite cos-board-tokens.css + index.css into a clean 3-layer token system: PRIMITIVES (Graphite neutral scale + Iris brand scale + status hues, OKLCH-derived) → SEMANTIC keys (surface/canvas|panel|raised|overlay|inset, border/subtle|default|strong, text/primary|secondary|muted|disabled, brand/solid|hover|text|tint|on-solid, focus/ring, status fg+tint) → both light AND dark value sets keyed identically. Default theme = dark (ThemeProvider). All --cos-* semantic aliases preserved/extended so existing Tailwind components follow automatically with zero component rewrites. AA contrast on every text/surface pair. make ui-build compiles clean.

## Read First
- src/core/web/ui/public/cos-board-tokens.css
- src/core/web/ui/src/index.css
- src/core/web/ui/src/design/ThemeProvider.tsx

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the Hub UI loads with no saved theme preference
- **When** any page renders in either light or dark mode
- **Then** every surface/text/border/accent resolves from the new 3-layer Cortex token set (Graphite neutrals + Iris brand), the default theme is dark, dark mode defines its own `--sticky-*` values (no light pastels bleeding onto the dark canvas), every text-on-surface pair meets WCAG 2.2 AA (≥4.5:1 body / ≥3:1 large), and `make ui-build` compiles with zero component edits

Spec SSOT: [docs/engineering/design-system.md](../engineering/design-system.md)

## Work Log
