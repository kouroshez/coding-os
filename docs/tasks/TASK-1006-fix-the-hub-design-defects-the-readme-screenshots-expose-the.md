---
id: TASK-1006
title: "Fix the Hub design defects the README screenshots expose, then reshoot every tab"
swimlane: core
kind: chore
epic: null
labels: [ui, design, docs-update, readme, ready]
status: "in_progress"
priority: P2
appetite: 1d
created: 2026-08-17
started: 2026-08-17
completed: null
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---

# TASK-1006: Fix the Hub design defects the README screenshots expose, then reshoot every tab

**Outcome (one sentence):** README shows the Hub honestly and well: empty board columns stop eating most of the width, the graph counter stops contradicting itself, chat rows stop printing raw byte sizes, and every tab is captured, compressed under 1 MB total, and documented.

## Read First

- `src/core/web/ui/src/features/cos-board/BoardGrid.tsx` · `BoardColumnHeaders.tsx` · `BoardCell.tsx` — the column layout (`flex: 1 1 0`, `minWidth: 190`) that gives an empty column the same width as a full one.
- `src/core/graph_os/tools/_graph_export.py` (meta block ~line 315) — budget provenance the Hub badge reads; `src/core/web/ui/src/features/graph/GraphCanvas.tsx` (node-count badge) is its only consumer.
- `src/core/web/ui/src/features/cognition/ChatList.tsx` — `formatSize()` prints the transcript's raw byte size in the chat row.
- `src/core/web/ui/src/pages/ConfigPage.tsx` — tab panel container; every other Hub page uses `max-w-7xl` (`layout/HubPrimitives.tsx`, `pages/HubHome.tsx`).
- `src/core/rules/api-contract-discipline.md` — the graph meta field is a producer/consumer contract; read the emit site, not the consumer.

## Acceptance

- **Given** a board where only two of seven columns hold cards, **when** the grid renders and nothing is being dragged, **then** the empty columns render as narrow rails and the populated columns share the freed width; **and** the rails widen back to full drop zones while a card is being dragged.
- **Given** the Hub Graph tab on a repo whose graph is larger than the depth budget, **when** the node-count badge renders, **then** it reads `shown / fetched of <graph_node_total> nodes` sourced from `meta.graph_node_total`, never a self-contradicting pair.
- **Given** a chat row, **when** the list renders, **then** no raw byte/kb/mb size is shown.
- **Given** the Config tab, **when** a table renders, **then** its container is the same `max-w-7xl` every other Hub page uses.

## Work Log
- 2026-08-17 [claude]: Edit ConfigPage.tsx
- 2026-08-17 [claude]: Edit ChatList.tsx
- 2026-08-17 [claude]: Edit ChatList.tsx
- 2026-08-17 [claude]: Edit ChatList.tsx
- 2026-08-17 [claude]: Edit ChatList.tsx
- 2026-08-17 [claude]: Edit DashboardPage.tsx
- 2026-08-17 [claude]: Edit _graph_export.py
- 2026-08-17 [claude]: Edit _graph_export.py
- 2026-08-17 [claude]: Edit _graph_export.py
- 2026-08-17 [claude]: Edit graph-adapter.ts
- 2026-08-17 [claude]: Edit GraphCanvas.tsx
- 2026-08-17 [claude]: Edit GraphCanvas.tsx
- 2026-08-17 [claude]: Edit GraphCanvas.tsx
- 2026-08-17 [claude]: Edit useBoardData.ts
- 2026-08-17 [claude]: Edit useBoardData.ts
- 2026-08-17 [claude]: Edit board-shared.tsx
- 2026-08-17 [claude]: Edit BoardColumnHeaders.tsx
- 2026-08-17 [claude]: Edit BoardColumnHeaders.tsx
- 2026-08-17 [claude]: Edit BoardCell.tsx
- 2026-08-17 [claude]: Edit BoardGrid.tsx
- 2026-08-17 [claude]: Edit BoardGrid.tsx
- 2026-08-17 [claude]: Edit BoardGrid.tsx
- 2026-08-17 [claude]: Edit BoardGrid.tsx
- 2026-08-17 [claude]: Edit BoardGrid.tsx
- 2026-08-17 [claude]: Edit BoardGrid.tsx
- 2026-08-17 [claude]: Edit BoardGrid.tsx
- 2026-08-17 [claude]: Edit probe_export_meta.py
- 2026-08-17 [claude]: Edit test_mcp_tools_export.py
- 2026-08-17 [claude]: Edit GraphCanvas.tsx
- 2026-08-17 [claude]: Edit GraphCanvas.tsx
- 2026-08-17 [claude]: Edit graph-adapter.ts
- 2026-08-17 [claude]: Edit graph-adapter.test.ts
- 2026-08-17 [claude]: Edit graph-adapter.test.ts
- 2026-08-17 [claude]: Edit _graph_export.py
- 2026-08-17 [claude]: Edit _graph_export.py
- 2026-08-17 [claude]: commit 3f7f8532e1 — feat(graph): report the whole-graph node total in export meta
- 2026-08-17 [claude]: commit 4c924c7259 — fix(hub): collapse empty board columns to a rail
- 2026-08-17 [claude]: commit a7c7cae519 — fix(hub): move the raw transcript byte size out of the chat row
- 2026-08-17 [claude]: commit 1cbe8e87eb — fix(hub): widen the Config tables to the Hub page width
- 2026-08-17 [claude]: Four Hub fixes landed (3f7f8532, 4c924c72, a7c7cae5, 1cbe8e87): empty board columns collapse to a 44px rail…
