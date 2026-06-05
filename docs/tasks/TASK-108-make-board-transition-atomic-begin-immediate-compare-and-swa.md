---
id: TASK-108
title: "Make board transition atomic — BEGIN IMMEDIATE + compare-and-swap + raw-sqlite helpers via get_connection"
swimlane: core
kind: bug
epic: hook-remediation
labels: [board, concurrency, sqlite, multi-agent, audit-n4]
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

# TASK-108: Make board transition atomic — BEGIN IMMEDIATE + compare-and-swap + raw-sqlite helpers via get_connection

**Outcome (one sentence):** workflow.transition wraps read+wip+update in BEGIN IMMEDIATE with a WHERE-status compare-and-swap; cos_task_move passes expected_from; 4 board hook helpers route through database.get_connection (WAL+busy_timeout).

## Read First
- src/core/board_os/workflow.py
- src/core/board_os/mcp_tools.py
- src/core/hooks/_helpers/task_sync.py

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
