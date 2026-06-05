---
id: TASK-162
title: "Cortex graph palette v2 — maximize node-kind color distinction (ΔE-verified)"
swimlane: core
kind: refactor
epic: ui-design-system
labels: [ui, graph, palette, a11y, ready]
status: complete
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
# TASK-162: Cortex graph palette v2 — maximize node-kind color distinction (ΔE-verified)

**Outcome (one sentence):** Replace NODE_COLORS (node-colors.ts) with a maximally-distinguishable categorical palette for the graph: 7 family hue-anchors spread across the wheel (structure=amber, code-defs=indigo/violet, code-refs=neutral gray, api=cyan, docs=green, governance=magenta/pink, analysis=orange) with BOLD lightness steps WITHIN each family (≥~12 L apart) instead of the subtle hue-only variation of v1 that made class/method/function (and route/tool/event) near-indistinguishable as small dots. Verify programmatically with a pairwise CIE Lab ΔE check — no two kinds (especially common ones) below the distinguishability threshold. Tuned for the dark canvas. make ui-build green.

## Read First
- src/core/web/ui/src/lib/node-colors.ts
- docs/engineering/design-system.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the knowledge graph renders node-kind dots on the dark canvas
- **When** two nodes of different kinds sit near each other
- **Then** their colors are easily distinguishable — every common-vs-common kind pair is ≥18 ΔE76 apart (verified via pairwise CIE-Lab check → GATE PASS), families occupy distinct hue regions (amber/indigo-violet/gray/cyan/green/magenta-pink/orange) and members differ by bold lightness steps, only the deliberately de-emphasized gray refs (import_/identifier/unknown) may cluster, and `make ui-build` is green

Spec SSOT: [docs/engineering/design-system.md](../engineering/design-system.md)

## Work Log
- 2026-06-05 [claude]: Shipped (commit 51f32e0): NODE_COLORS v2 — families on distinct hue regions (structure=amber, code-defs=indigo→violet, r
