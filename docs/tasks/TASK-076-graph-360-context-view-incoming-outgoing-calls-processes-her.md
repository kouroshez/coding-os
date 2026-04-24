---
id: TASK-076
title: "Graph: 360° Context view (incoming/outgoing calls, processes, heritage) per symbol"
swimlane: graph-os
kind: feature
epic: graph-os-graph-tool-parity
labels: [hub, graph, ui, P2-ux-parity]
status: icebox
priority: P2
appetite: "4h"
created: 2026-04-24
started: null
completed: null
agent_session: null
depends_on: [TASK-075, TASK-083]
blocked_by: []
references: []
---

# TASK-076: Graph — 360° Context view per symbol

**Outcome (one sentence):** The Inspector's "Context" tab shows, for any selected symbol: incoming calls and imports, outgoing calls, heritage chain (extends/implements), and membership in named processes (from TASK-075) — reaching parity with graph-tool's `context` tool in a single screen.

## Read First

- [core/web/ui/src/layout/Inspector.tsx](../../core/web/ui/src/layout/Inspector.tsx) — host for the new tab.
- [core/graph_os/tools/](../../core/graph_os/tools/) — `cos_graph_context` backend; aggregates calls/imports/heritage.
- [core/graph_os/extractors/code_python.py](../../core/graph_os/extractors/code_python.py) — confirms heritage edges exist; TS coverage pending TASK-077.
- graph-tool `context` tool reference (Phase P2 analysis).

## Acceptance (G/W/T) — *this IS the Definition of Done*

- **Given** any selected symbol in the Graph tab
  **When** the user opens Inspector → "Context"
  **Then** five sections render in order: **Heritage** (extends / implements chain, clickable), **Incoming calls** (top 20 by confidence, with file:line), **Incoming imports**, **Outgoing calls**, **Member of processes** (from TASK-075; empty if no clusters).
- **Given** a class with 3 parents / 5 implemented interfaces
  **When** Heritage renders
  **Then** the chain shows as a left-to-right ribbon with arrow glyphs, each node clickable to re-scope the view to that target.
- **Given** a symbol with no inbound callers
  **When** rendered
  **Then** the "Incoming calls" section shows a friendly empty state ("No callers in the indexed graph — entry point?") that links to TASK-081's entry-point list.
- **Given** a symbol that is a member of process `LoginFlow` at step 3
  **When** rendered
  **Then** the process appears with a mini-breadcrumb `steps 1 → 2 → **3 (this)** → 4 → 5` that is clickable.
- **Tests:** Playwright `e2e/graph-context.spec.ts` asserts every section renders and links navigate correctly; empty-state path covered.

## Implementation Notes

1. New component `features/graph/ContextPanel.tsx` with sub-sections as `<details>` elements (all expanded by default for ≤ 5 items each, collapsed when > 5).
2. Single-shot request `GET /api/p/<slug>/graph/context?node=<id>` returns the full payload — no N+1 requests.
3. Consistency: same edge-kind icon set as TASK-074 so users learn one visual vocabulary.
4. Keyboard: `[` / `]` cycles through heritage chain, `j` / `k` through incoming/outgoing lists — document in Help popover.
5. The "Member of processes" section stays hidden (not empty-state) when TASK-075 hasn't shipped and no processes exist at all — don't advertise a feature we don't have.

## Dependencies

- **Depends on:** TASK-075 (for process membership section; section auto-hides if feature flag off), TASK-083 (type annotations unlock richer incoming/outgoing resolution).
- **Unblocks:** nothing directly, but materially improves TASK-078 (rename preview) UX.

## Work Log
