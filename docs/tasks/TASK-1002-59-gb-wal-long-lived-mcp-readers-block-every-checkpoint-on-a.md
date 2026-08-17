---
id: TASK-1002
title: "59 GB WAL \u2014 long-lived MCP readers block every checkpoint on a 92%-full disk"
swimlane: core
kind: bug
epic: null
labels: [infra, database, reliability, ready]
status: icebox
priority: P1
appetite: 1d
created: 2026-08-17
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-1002: 59 GB WAL — long-lived MCP readers block every checkpoint on a 92%-full disk

**Outcome (one sentence):** The WAL stays bounded during normal operation: long-lived MCP/Hub connections no longer pin a read snapshot indefinitely, so wal_autocheckpoint can actually drain, and a locked-DB write waits instead of raising OperationalError.

## Read First
- src/core/thinking_os/_db_pool.py
- docs/engineering/state-files.md

## Repro Steps
1. `ls -la .coding-os/coding-os.db*` → db 342M, **db-wal 59G**, db-shm 115M. 2. `df -h .` → 32Gi available on a 92%-full volume, i.e. less free space than the WAL itself. 3. `lsof .coding-os/coding-os.db` → two long-lived `src/core/thinking_os/server.py` processes (one per Claude panel) hold it open; `cos hub restart` did NOT shrink the WAL because these, not Hub, pin the snapshot. 4. `PRAGMA wal_autocheckpoint` → 1000 (set correctly by _db_pool.apply_pragmas), so the cap is configured and simply never reachable. 5. `cos errors` → `tool cos_work_log_append raised OperationalError` at 2026-08-16T23:01:10Z, the write-side symptom.

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** two MCP server processes and Hub attached to one project DB
**When** the system runs for a normal working day
**Then** `.coding-os/coding-os.db-wal` stays within the state-size budget instead of growing without bound.

**Given** a pooled connection that has served a read
**When** it sits idle between tool calls
**Then** it does not hold a read snapshot that blocks checkpointing.

**Given** the current 59 GB WAL
**When** the documented recovery step runs
**Then** it drains safely on a volume with less free space than the WAL, or the step explicitly refuses and says why.

## Work Log
