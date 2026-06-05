---
id: TASK-168
title: "Thread explicit agent_session through cos_task MCP args to fix wrong-panel attribution"
swimlane: core
kind: bug
epic: agent-hub
labels: [ready]
status: icebox
priority: P1
appetite: "1d"
created: 2026-06-05
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-168: Thread explicit agent_session through cos_task MCP args to fix wrong-panel attribution

**Outcome (one sentence):** MCP task ops attribute to the calling panel (not last-writer), killing false WIP blocks and mis-reclaim under concurrent same-agent panels.

## Read First
- docs/engineering/agent-hub-orchestration.md
- src/core/board_os/_agent_runtime.py
- src/core/board_os/mcp_tools.py
- docs/engineering/state-files.md

## Repro Steps
1. (fill in: exact steps to reproduce)
2. ...
Expected: ...
Actual: ...

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** ...
- **When** ...
- **Then** ...

## Work Log
