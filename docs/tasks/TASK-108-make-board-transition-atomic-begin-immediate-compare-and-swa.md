---
id: TASK-108
title: "Make board transition atomic — BEGIN IMMEDIATE + compare-and-swap + raw-sqlite helpers via get_connection"
swimlane: core
kind: bug
epic: hook-remediation
labels: [board, concurrency, sqlite, multi-agent, audit-n4, ready]
status: archive
priority: P1
appetite: "1d"
created: 2026-06-05
started: 2026-06-05
completed: 2026-06-05
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-108: Make board transition atomic — BEGIN IMMEDIATE + compare-and-swap + raw-sqlite helpers via get_connection

**Outcome (one sentence):** `workflow.transition` performs the status re-check, WIP count, and row UPDATE inside one `BEGIN IMMEDIATE` critical section with a CAS-guarded UPDATE (`WHERE task_id=? AND status=?` + rowcount check), and the four board helpers open their connections through `get_connection` (WAL + busy_timeout).

## Read First
- src/core/board_os/workflow.py
- src/core/board_os/mcp_tools.py
- src/core/thinking_os/database.py (get_connection)

## Repro Steps
1. Two sessions call `cos_task_move` on the same task concurrently. Each reads `status` (entry SELECT), validates (file I/O widens the window), then blindly `UPDATE ... WHERE task_id=?` — last writer wins, board state corrupts, WIP cap can be exceeded by 1.
2. The 4 helpers (work_log_append, wip_limit_check, transition_gates_cli, task_sync) open `sqlite3.connect(db)` with no busy_timeout → immediate "database is locked" under contention.
Expected: a concurrent transition either serializes or returns a clean transient conflict; helpers wait on a lock.
Actual: read→write + count→write races; helpers fail fast on lock.

## Acceptance (G/W/T)
- **Given** `workflow.transition`, **When** it writes, **Then** the status re-check + WIP count + UPDATE + MD write + history INSERT run inside one `BEGIN IMMEDIATE`, the UPDATE is CAS-guarded (`AND status=?`), and a rowcount≠1 or status drift returns `transient`.
- **Given** a peer changed the row during the lock-free gate phase, **When** the lock is acquired, **Then** the re-SELECT detects it and returns a transient conflict (no corruption).
- **Given** the 4 board helpers, **When** they open the DB, **Then** they route through `get_connection` (WAL + busy_timeout) with a `timeout=5s`+`PRAGMA busy_timeout` fallback.
- **Given** consume_override, **When** two hooks consume the same one-shot override, **Then** an exclusive flock serializes the read-modify-write.

## Work Log
- 2026-06-05 [claude]: 4a workflow.transition write path now one BEGIN IMMEDIATE critical section (re-SELECT under lock + WIP-under-lock + CAS 
