---
id: TASK-773
title: "Fix Hub board work-log data loss on task-body edit; wire search deep-link to focus a task; align AttentionBell events"
swimlane: core
kind: bug
epic: null
labels: [ready]
status: in_progress
priority: P1
appetite: 1d
created: 2026-07-04
started: 2026-07-04
completed: null
agent_session: ses-claude-20260703-210450-473d
depends_on: []
blocked_by: []
references: []
---
# TASK-773: Fix Hub board work-log data loss on task-body edit; wire search deep-link to focus a task; align AttentionBell events

**Outcome (one sentence):** Editing a task body through the board UI no longer silently deletes its ## Work Log section (the biggest defect: real data loss). The search 'open in board' action lands on the board with the task focused. AttentionBell only advertises event types the stream actually emits (no dead affordance).

## Read First
- src/core/web/ui/src/features/cos-board/CosBoardPage.tsx
- src/core/board_os/mcp_tools.py
- src/core/web/ui/src/features/search/UnifiedSearch.tsx
- src/core/web/ui/src/features/attention/AttentionBell.tsx

## Repro Steps
Open a task with a ## Work Log in the board, click Edit, Save without changes → the Work Log section is gone (data loss). Search a task, click 'open in board' → lands on board without focusing the task (query dropped + no reader). AttentionBell lists agent-blocked/needs-input which stream.py never emits.

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a task whose body has a ## Work Log section **When** it is edited and saved through the board UI **Then** the persisted body still contains the Work Log. **Given** a memory/task search hit **When** 'open in board' is clicked **Then** the board opens with that task focused (query survives the redirect and the board reads it). **Given** the SSE stream never emits agent-blocked/needs-input **When** AttentionBell mounts **Then** it does not subscribe to event types nothing emits.

## Work Log
- 2026-07-04 [claude]: Edit task-lifecycle.md
- 2026-07-04 [claude]: Edit mcp_tools.py
- 2026-07-04 [claude]: Edit mcp_tools.py
- 2026-07-04 [claude]: Edit test_mcp_tools.py
- 2026-07-04 [claude]: 5c (critical data loss): cos_task_edit now preserves the ## Work Log section when an incoming body omits it — an SSOT…
