---
id: TASK-322
title: "Hub: task-pick suggestion surface \u2014 consume /api/board/pick (highest-impact next task) in the board UI"
swimlane: core
kind: feature
epic: null
labels: [hub-ui, audit-2026-06-09, ready]
status: testing
priority: P3
appetite: 1d
created: 2026-06-10
started: 2026-06-10
completed: null
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-322: Hub: task-pick suggestion surface — consume /api/board/pick (highest-impact next task) in the board UI

**Outcome (one sentence):** The board page offers a "Suggest next task" action that calls the existing /api/board/pick route and presents the ranked suggestion with its reason — today the route has zero UI consumers.

## Read First
- src/core/web/routes/board.py (/api/board/pick producer — copy exact field names, api-contract-discipline)
- src/core/web/ui/src/features/cos-board/CosBoardPage.tsx (placement)
- src/core/rules/api-contract-discipline.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a board with ≥1 ready task
- **When** the user clicks Suggest next task
- **Then** the pick result renders with task id, title, and reason, and a click navigates to the task drawer
- **Given** an empty ready queue
- **When** pick returns no candidate
- **Then** the UI states that explicitly (no silent empty panel)
- **Given** the producer response shape
- **When** the UI types are written
- **Then** field names are verified against board.py's actual emit (no drift), with a component test

## Work Log
- 2026-06-10 [claude]: Shipped (score 9/10): board header gains "suggest next" — lazy GET /api/board/pick (producer shape verified at the emit 
