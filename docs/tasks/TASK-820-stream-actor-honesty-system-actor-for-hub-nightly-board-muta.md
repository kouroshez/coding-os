---
id: TASK-820
title: "Stream actor honesty: system actor for hub/nightly board mutations (auto-archive, reclaim, SSE row show as H)"
swimlane: core
kind: bug
epic: null
labels: [hub, board, stream, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-07-16
started: 2026-07-16
completed: 2026-07-16
agent_session: ses-claude-20260716-145309-8189
depends_on: []
blocked_by: []
references: []
---
# TASK-820: Stream actor honesty: system actor for hub/nightly board mutations (auto-archive, reclaim, SSE row show as H)

**Outcome (one sentence):** Unattended board mutations (nightly auto-archive/reclaim) and the SSE-online banner render a gray `Sy` system pip in the AGENT STREAM panel instead of the green human `H`; human attribution is reserved for genuine panel actions.

## Read First
- docs/engineering/hub-architecture.md
- src/core/board_os/_agent_runtime.py
- src/core/web/ui/src/features/cos-board/useBoardStream.ts

## Repro Steps
Enable complete_auto_archive_days, let the nightly reclaim leg archive idle tasks, open Hub board AGENT STREAM: every `complete -> archive (auto-archive: ...)` row shows the H human pip although no human touched the panel.

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** the nightly `_archive_stale_sweep`/`cos_task_reclaim` transitions a task **When** the stream panel renders the event **Then** the pip is `system` (not human) and task history labels the actor `system`.
**Given** the SSE connection banner row **When** it is pushed locally **Then** its agent is `system`.
**Given** a genuine panel drag/create **When** rendered **Then** it still attributes to `human`.

## Work Log
- 2026-07-16 [claude]: Edit hub-architecture.md
- 2026-07-16 [claude]: Edit _agent_runtime.py
- 2026-07-16 [claude]: Edit _agent_runtime.py
- 2026-07-16 [claude]: Edit _agent_runtime.py
- 2026-07-16 [claude]: Edit mcp_tools.py
- 2026-07-16 [claude]: Edit mcp_tools.py
- 2026-07-16 [claude]: Edit mcp_tools.py
- 2026-07-16 [claude]: Edit mcp_tools.py
- 2026-07-16 [claude]: Edit board.py
- 2026-07-16 [claude]: Edit CosBoardPage.tsx
- 2026-07-16 [claude]: Edit CosBoardPage.tsx
- 2026-07-16 [claude]: Edit CosBoardPage.tsx
- 2026-07-16 [claude]: Edit useBoardStream.ts
- 2026-07-16 [claude]: Edit test_mcp_tools.py
- 2026-07-16 [claude]: Edit useBoardStream.test.ts
- 2026-07-16 [claude]: Edit test_mcp_tools.py
- 2026-07-16 [claude]: Root cause: _archive_stale_sweep/reclaim wrote agent_session=NULL and the UI maps NULL→human. Fix: ses-system-*…
