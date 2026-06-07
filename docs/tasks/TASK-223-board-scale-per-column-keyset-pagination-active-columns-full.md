---
id: TASK-223
title: "Board scale: per-column keyset pagination (active columns full; complete/archive paged with cursor+total) + SPA virtual scroll \u2014 supersede interim apply_budget"
swimlane: "board_os"
kind: feature
epic: enterprise-scale
labels: [scale, board, web, pagination, ready]
status: icebox
priority: P0
appetite: 3d
created: 2026-06-07
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-223: Board scale: per-column keyset pagination (active columns full; complete/archive paged with cursor+total) + SPA virtual scroll — supersede interim apply_budget

**Outcome (one sentence):** The board never loads more than a page per column at any task count: cos_task_board returns active columns in full (bounded by WIP) but complete/archive via keyset pagination (cursor on completed_at/last_transition_at + per-column total); board_list exposes cursor/limit; the React kanban + graph use virtual scrolling + load-more. Replaces the interim apply_budget=False return-all (TASK-220). Verified by a 50K-task soak returning bounded payloads with no truncation surprise. See audit-enterprise-scale-2026-06-07.md (board_os findings).

## Read First
- docs/tasks/audits/audit-enterprise-scale-2026-06-07.md
- src/core/board_os/mcp_tools.py
- src/core/web/ui/src/features/cos-board/CosBoardPage.tsx

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a board with far more complete/archive cards than one page (e.g. 50K complete).
- **When** cos_task_board / board_list returns a column and the SPA renders it.
- **Then** active columns return in full (WIP-bounded) while complete/archive return ONE keyset page (cursor + per-column total_count, no apply_budget return-all), the kanban + graph virtual-scroll with load-more, and a 50K-task soak yields bounded payloads (each page << prior 398KB) with honest truncated/total — replacing the TASK-220 interim fix.

## Work Log
