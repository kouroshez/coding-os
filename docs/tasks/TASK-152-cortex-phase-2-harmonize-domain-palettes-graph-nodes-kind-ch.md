---
id: TASK-152
title: "Cortex Phase 2 — harmonize domain palettes (graph nodes + kind chips)"
swimlane: core
kind: refactor
epic: ui-design-system
labels: [ui, design-system, graph, palette, ready]
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
# TASK-152: Cortex Phase 2 — harmonize domain palettes (graph nodes + kind chips)

**Outcome (one sentence):** Rewrite NODE_COLORS (node-colors.ts) so every graph node-kind sits at equal OKLCH lightness (~0.72) and chroma (~0.14) — only hue distinguishes a category (structure=steel, code-defs=Iris, api=azure, docs=teal, governance=gold/magenta, analysis=violet). Kills the legacy chaos where near-black brown sat beside hot orange. Retune KIND_COLORS chips (kindColors.ts) so the chip label reads on the new dark task-kind tints (AA). make ui-build green.

## Read First
- src/core/web/ui/src/lib/node-colors.ts
- src/core/web/ui/src/features/cos-board/kindColors.ts
- docs/engineering/design-system.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the graph canvas and the Scrumban board render in dark mode (the default)
- **When** node-kind dots and task-kind chips are painted
- **Then** every graph node-kind color sits at near-equal lightness/chroma (hue-only separation — no near-black-brown beside hot-orange chaos), every task-kind chip is sourced from a themed `--kind-*` token that meets AA on its dark tint, no hardcoded light hex bleeds into dark mode, and `make ui-build` is green

Spec SSOT: [docs/engineering/design-system.md](../engineering/design-system.md)

## Work Log
