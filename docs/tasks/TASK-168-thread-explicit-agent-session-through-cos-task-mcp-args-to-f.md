---
id: TASK-168
title: "Thread explicit agent_session through cos_task MCP args to fix wrong-panel attribution"
swimlane: core
kind: bug
epic: agent-hub
labels: [ready]
status: complete
priority: P1
appetite: "1d"
created: 2026-06-05
started: 2026-06-05
completed: 2026-06-05
agent_session: ses-claude-20260605-183120-db30
depends_on: []
blocked_by: []
references: []
---
# TASK-168: Thread explicit agent_session through cos_task MCP args to fix wrong-panel attribution

**Outcome (one sentence):** MCP task ops attribute to the calling panel (not the shared `ses-<agent>-pid<server-pid>` synthetic), killing false WIP blocks and mis-reclaim under concurrent same-agent panels.

## Read First
- docs/engineering/agent-hub-orchestration.md
- src/core/board_os/_agent_runtime.py
- src/core/hooks/session-context.sh
- docs/engineering/state-files.md

## Repro Steps
1. Two Claude panels active on one project; each calls `cos_task_move` to start a task WITHOUT passing agent_session.
2. The long-lived MCP server has an empty `$COS_SESSION_FILE`, so `resolve_agent_session` falls to `ses-<agent>-pid<server-pid>` — the SAME id for both panels.
Expected: each task attributed to its own panel; per_session_wip counts per panel.
Actual: both in_progress tasks count under one synthetic session → second panel falsely blocked by WIP cap; reclaim mis-judges ownership. (Observed: tasks carrying `agent_session: ses-claude-pid383`.)

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** an MCP-server call with no explicit agent_session and no `$COS_SESSION_FILE`
- **When** `resolve_agent_session` runs
- **Then** it returns the agent-level `.active-session` pointer (the current panel, refreshed each prompt by session-context.sh) instead of the server-pid synthetic; an explicit arg still wins; unit tests cover both.

## Work Log
- 2026-06-05 [claude]: resolve_agent_session now reads the agent-level .active-session pointer before the synthetic pid fallback, so MCP-create
