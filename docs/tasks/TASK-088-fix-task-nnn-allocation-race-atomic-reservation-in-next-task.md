---
id: TASK-088
title: "Fix TASK-NNN allocation race — atomic reservation in _next_task_id"
swimlane: infra
kind: bug
epic: null
labels: [board, concurrency, race, ready]
status: archive
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
# TASK-088: Fix TASK-NNN allocation race — atomic reservation in _next_task_id

**Outcome (one sentence):** Two concurrent cos_task_create calls can never receive the same TASK-NNN id; allocation is atomic at the SQLite write-lock level.

## Read First
- src/core/board_os/mcp_tools.py
- src/core/board_os/sync.py

## Repro Steps
1. Two agent sessions call cos_task_create within the same few-ms window.
2. Both `_next_task_id` reads run `SELECT MAX(...)` before either writes its DB row.
Expected: each create gets a distinct TASK-NNN.
Actual: both compute the same max+1 → duplicate TASK-NNN; the second file/sync overwrites the first.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** N concurrent cos_task_create calls against one DB
- **When** each allocates an id via `_next_task_id`
- **Then** every returned TASK-NNN is unique — allocation reserves the row in a single atomic INSERT…SELECT, so SQLite's write lock serializes contenders (verified by a concurrency test).

## Work Log
- 2026-06-04 [claude]: _next_task_id now reserves via a single atomic INSERT…SELECT (max(db,fs)+1) so SQLite's write lock serializes concurrent
