---
id: TASK-1008
title: "Cap SQLite WAL growth \u2014 journal_size_limit + SessionStart WAL guard"
swimlane: infra
kind: bug
epic: null
labels: [incident, sqlite, disk, ready]
status: complete
priority: P0
appetite: 1d
created: 2026-08-17
started: 2026-08-17
completed: 2026-08-17
agent_session: ses-claude-20260817-154319-10c2
depends_on: []
blocked_by: []
references: []
---
# TASK-1008: Cap SQLite WAL growth — journal_size_limit + SessionStart WAL guard

**Outcome (one sentence):** coding-os.db-wal can never again grow unbounded and silently fill the disk; when a checkpoint is blocked the operator is told which PID to kill.

## Read First
- src/core/thinking_os/_db_pool.py
- src/core/hooks/auto-brain-decay.sh
- docs/engineering/state-files.md

## Repro Steps
.coding-os/coding-os.db-wal reached 59.29 GB against a 342 MB DB (shm 115 MB), taking the boot volume to 92% full. `PRAGMA wal_checkpoint(PASSIVE)` returned `(0, 531, 531)` — only 531 live frames, so checkpointing was NOT blocked at probe time; the file was pure never-truncated high-water mark because `journal_size_limit = -1` on every connection. Growth window traced to stale MCP server processes (pid 7113 up 11d20h, 42422 5d22h, 87397 4d22h) holding read snapshots that blocked checkpoints.

## Acceptance (G/W/T) — *this IS the Definition of Done*

- **Given** a long-lived connection opened through `apply_pragmas`, **When** it performs a WAL checkpoint, **Then** the `-wal` file is truncated back to the `journal_size_limit` cap instead of keeping its high-water size.
- **Given** a `-wal` larger than the guard threshold at SessionStart, **When** `auto-brain-decay.sh` runs, **Then** it forces `PRAGMA wal_checkpoint(TRUNCATE)` and logs the reclaimed bytes.
- **Given** that forced TRUNCATE returns `busy=1`, **When** the guard reports, **Then** stderr names the PIDs still holding the `-wal` open so the operator can clear the blocker.

## Work Log
- 2026-08-17 [claude]: Edit state-files.md
- 2026-08-17 [claude]: Plan: two layers, not one. The connection-level `journal_size_limit` cap (32 MB, in the `apply_pragmas` SSOT that…
- 2026-08-17 [claude]: Edit _db_pool.py
- 2026-08-17 [claude]: Edit _db_pool.py
- 2026-08-17 [claude]: Edit wal_guard.py
- 2026-08-17 [claude]: Edit auto-brain-decay.sh
- 2026-08-17 [claude]: Edit auto-brain-decay.sh
- 2026-08-17 [claude]: Edit verify_wal_guard.py
- 2026-08-17 [claude]: Edit verify_wal_guard.py
- 2026-08-17 [claude]: Edit probe_limit.py
- 2026-08-17 [claude]: Edit verify_wal_guard.py
- 2026-08-17 [claude]: Edit _db_pool.py
- 2026-08-17 [claude]: Edit state-files.md
- 2026-08-17 [claude]: Edit test_wal_guard.py
- 2026-08-17 [claude]: Edit smoke_hook.py
- 2026-08-17 [claude]: Edit test_wal_guard.py
- 2026-08-17 [claude]: Edit _db_pool.py
- 2026-08-17 [claude]: Edit auto-brain-decay.sh
- 2026-08-17 [claude]: commit 1e52086211 — fix(db): cap WAL growth with journal_size_limit and a SessionStart WAL guard
- 2026-08-17 [claude]: Shipped both layers. Measured finding that changed the design writeup: on SQLite 3.50.4 `journal_size_limit` lands at…
- 2026-08-17 [claude]: Status transitioned to complete via cos task-done.
