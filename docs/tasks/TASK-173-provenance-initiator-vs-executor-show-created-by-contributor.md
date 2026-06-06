---
id: TASK-173
title: "Provenance initiator vs executor + show created-by/contributors in task UI"
swimlane: core
kind: feature
epic: agent-hub
labels: [ready]
status: complete
priority: P2
appetite: "1d"
created: 2026-06-05
started: 2026-06-05
completed: 2026-06-05
agent_session: ses-claude-20260605-183120-db30
depends_on: []
blocked_by: []
references: []
---
# TASK-173: Provenance initiator vs executor + show created-by/contributors in task UI

**Outcome (one sentence):** Tasks distinguish the human initiator (who triggered) from the agent executor (session/adapter/model); a manual web create is attributed to the human, and the detail modal surfaces created-by + last-edited-by + contributors from the append-only history.

## Read First
- docs/engineering/agent-hub-orchestration.md
- src/core/web/routes/board.py
- src/core/board_os/mcp_tools.py
- src/core/web/ui/src/features/cos-board/CosBoardPage.tsx

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a task created manually from the web panel and later edited by a different actor
- **When** the user opens the task detail
- **Then** the creation is attributed to the human initiator (not an arbitrary agent panel), every edit is an append-only history row, and the modal clearly shows created-by, last-edited-by, and contributors (from cos_task_history); board_os tests + make ui-build green.

## Work Log
- 2026-06-06 [claude]: Web manual create now attributes to the human initiator (board.py defaults agent_session to human_actor when none given)
