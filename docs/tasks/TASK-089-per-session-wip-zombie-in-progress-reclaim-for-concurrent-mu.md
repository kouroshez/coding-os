---
id: TASK-089
title: "Per-session WIP + zombie in_progress reclaim for concurrent multi-agent work"
swimlane: infra
kind: feature
epic: null
labels: [board, concurrency, wip, multi-agent, ready]
status: complete
priority: P1
appetite: "1d"
created: 2026-06-04
started: 2026-06-04
completed: 2026-06-04
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-089: Per-session WIP + zombie in_progress reclaim for concurrent multi-agent work

**Outcome (one sentence):** Concurrent agent sessions no longer block each other on the global in_progress cap (WIP scoped per agent_session), and in_progress tasks orphaned by a dead session are reclaimed to the pullable queue.

## Read First
- src/core/board_os/workflow.py
- src/core/board_os/config.py
- src/core/board_os/mcp_tools.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** session A already has a task in_progress and `workflow_policy.per_session_wip=true`
- **When** session B (different agent_session) starts its own task
- **Then** B is NOT blocked by A's in_progress cap — WIP is counted per agent_session for in_progress.
- **Given** an in_progress task whose owning session is no longer active (presence stale) and older than the reclaim threshold
- **When** `cos_task_reclaim` runs (manually or at SessionStart)
- **Then** the orphaned task returns to icebox with the `ready` label and the reclaim is recorded in task_status_history.

## Work Log
- 2026-06-04 [claude]: Per-session in_progress WIP (check_wip scoped by agent_session) so concurrent sessions don't block; cos_task_reclaim op 
