---
id: TASK-323
title: "Hub: graph refactor panel \u2014 surface rename-plan / impact / contracts routes (zero UI today)"
swimlane: core
kind: feature
epic: null
labels: [hub-ui, graph, audit-2026-06-09, ready]
status: icebox
priority: P3
appetite: 1d
created: 2026-06-10
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-323: Hub: graph refactor panel — surface rename-plan / impact / contracts routes (zero UI today)

**Outcome (one sentence):** The graph page gains a refactor-planning panel: pick a symbol, see rename-plan touchpoints, impact tiers, and contract surface from the existing /api/graph/{rename-plan,impact,contracts} routes — blast-radius becomes visual for humans before approving agent refactors.

## Read First
- src/core/web/routes/graph.py (the three producers — exact field names)
- src/core/web/ui/src/features/graph/ContextPanel.tsx · ImpactPanel.tsx (existing panel patterns to extend, not duplicate — Rule 22 reuse-first)
- src/core/rules/api-contract-discipline.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a resolvable symbol selected on the graph page
- **When** the user opens the refactor panel
- **Then** rename-plan touchpoints (code/docs/tests/strings) and impact tiers render from live routes, with counts matching the API totals (truncation surfaced, never silent)
- **Given** an unresolvable selection
- **When** the panel queries
- **Then** the envelope error renders as a visible message
- **Given** existing panels
- **When** the diff lands
- **Then** shared fetch/render logic is reused — no third copy of panel plumbing

## Work Log
