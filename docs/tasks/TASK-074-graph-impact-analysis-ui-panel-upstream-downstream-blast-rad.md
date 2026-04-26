---
id: TASK-074
title: "Graph: impact analysis UI panel (upstream/downstream blast-radius with confidence ranking)"
swimlane: graph_os
kind: feature
epic: graph_os-the upstream scope-resolution implementation
labels: [hub, graph, ui, P2-ux-parity]
status: icebox
priority: P2
appetite: "6h"
created: 2026-04-24
started: null
completed: null
agent_session: null
depends_on: [TASK-077]
blocked_by: []
references: []
---

# TASK-074: Graph — impact analysis UI (upstream/downstream blast-radius)

**Outcome (one sentence):** The Graph tab inspector shows `UPSTREAM` and `DOWNSTREAM` trees with depth-1/2/3 badges, a `CALLS / IMPORTS / EXTENDS / IMPLEMENTS` edge-kind filter, and a confidence percentage per leaf — reaching visual parity with the upstream graph tooling's `impact` tool.

## Read First

- [core/web/ui/src/features/graph/](../../core/web/ui/src/features/graph/) — existing graph tab (Sigma viewer, ContainsTree, FilterBar).
- [core/web/ui/src/layout/Inspector.tsx](../../core/web/ui/src/layout/Inspector.tsx) — the side panel this task lives in.
- [core/graph_os/tools/](../../core/graph_os/tools/) — `cos_graph_impact` backend tool (already returns upstream / downstream; UI consumer missing).
- [core/web/routes/graph.py](../../core/web/routes/graph.py) — HTTP wrapper the UI calls.
- Reference: external graph tooling impact tool output shape (Phase P2 analysis, session `ad8ed04b`).

## Acceptance (G/W/T) — *this IS the Definition of Done*

- **Given** a selected node in the Graph tab
  **When** the user clicks the "Impact" sub-tab of Inspector
  **Then** two collapsible trees render: **Upstream (who depends on me)** and **Downstream (what I depend on)**, each showing depth 1 expanded by default, with chevrons to drill into depth 2/3, and a total count badge per depth.
- **Given** each tree leaf
  **When** rendered
  **Then** it displays: edge-kind icon (→ CALLS / ⇢ IMPORTS / ▲ EXTENDS / ◇ IMPLEMENTS), target node name, path:line, confidence bar (0–100%), and `source` provenance (`tree-sitter` / `lsp` / `text-search-fallback`).
- **Given** the FilterBar
  **When** the user toggles CALLS off
  **Then** both trees filter out CALLS edges immediately (client-side; no refetch).
- **Given** a node with > 200 upstream callers
  **When** the panel opens
  **Then** only top-50 by confidence render, with a "show all N" button that lazy-loads the rest via pagination (`?cursor=…`).
- **Tests:** Playwright spec `e2e/graph-impact.spec.ts` — asserts upstream/downstream render, filter toggles, deep-link URL `?node=<id>&tab=impact` restores state.
- **Backend tests:** existing `cos_graph_impact` tests cover the envelope; add a thin FastAPI route test.

## Implementation Notes

1. New component `features/graph/ImpactPanel.tsx` with two `<DepthTree>` subcomponents.
2. Data source: `GET /api/p/<slug>/graph/impact?node=<id>&direction=upstream|downstream&depth=3`.
3. Use existing `--board` / `--ink` / `--accent` design tokens (TASK-070 completed) — no hardcoded hex.
4. Confidence bar is a thin horizontal bar, coloured from `--accent` at 100% fading to `--ink-soft` at 0% — no red/yellow/green (we don't want semantic noise).
5. Deep-link friendly: panel state serialises to the URL `?node=X&tab=impact&depth=2` so links can be shared in the Board work-log.
6. Empty state (graph not indexed) reuses the same "Run `cos graph-reindex`" message as ContainsTree.

## Dependencies

- **Depends on:** TASK-077 (multi-lang) for the feature to be useful on non-Python repos; TASK-073 (reindex endpoint, complete) for the "Reindex" button.
- **Unblocks:** part of P2 UX parity triad (TASK-074 + TASK-076 + TASK-078).

## Work Log
