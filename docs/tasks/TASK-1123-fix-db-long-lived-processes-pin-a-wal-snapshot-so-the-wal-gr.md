---
id: TASK-1123
title: "fix(db): long-lived processes pin a WAL snapshot, so the WAL grows without bound and writes fail as locked"
swimlane: "thinking_os"
kind: bug
epic: null
labels: [ready]
status: complete
priority: P0
appetite: 1d
created: 2026-11-24
started: 2026-11-24
completed: 2026-11-24
agent_session: ses-claude-20261123-135444-89e7
depends_on: []
blocked_by: []
references: []
---
# TASK-1123: fix(db): long-lived processes pin a WAL snapshot, so the WAL grows without bound and writes fail as locked

**Outcome (one sentence):** No coding-os process can hold a read snapshot past one tool call, so checkpoints complete, the WAL stays under its 32 MB cap and a long-lived MCP server never fails a write with database is locked.

## Read First
- src/core/thinking_os/_db_pool.py
- src/core/graph_os/backends/_sqlite_connection.py
- src/core/thinking_os/tools/_shared.py
- docs/engineering/state-files.md

## Repro Steps
2026-11-24: coding-os.db 334 MB beside a 9.87 GB -wal; PRAGMA wal_checkpoint(PASSIVE) -> log 2396522, checkpointed 874. A 26h-old MCP server failed cos_work_log_append/cos_task_create with database is locked while a fresh process wrote fine (SQLITE_BUSY_SNAPSHOT). Same shape as the earlier 59 GB incident in state-files.md.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** an MCP tool call has returned, **When** a second connection runs wal_checkpoint(PASSIVE), **Then** checkpointed equals log frames.
- **Given** a server process older than an hour, **When** it appends a work-log line, **Then** the write succeeds.
- **Given** the fix is live and the stale servers restarted, **When** the WAL is measured, **Then** it is under 32 MB.

## Work Log
- 2026-11-24 [claude]: commit bec4ca16d7 — fix(db): a write that loses a lock race no longer pins the WAL for the life of the process
- 2026-11-25 [claude]: pre-fix MCP servers + hub restarted; TRUNCATE checkpoint reclaimed the 14 GB WAL, quick_check ok
- 2026-11-25 [claude]: commit 184f202326 — refactor(db): drop restating comments around the open-transaction release
- 2026-11-25 [claude]: live: new MCP server holding the DB, WAL 66 KB, PASSIVE checkpoint 16/16; lint+size ran after trim
- 2026-11-25 [claude]: Status transitioned to complete via cos task-done.
