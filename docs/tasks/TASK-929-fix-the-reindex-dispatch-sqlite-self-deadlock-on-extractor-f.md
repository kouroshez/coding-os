---
id: TASK-929
title: "Fix the reindex_dispatch SQLite self-deadlock on extractor failure"
swimlane: "graph_os"
kind: bug
epic: null
labels: [ready]
status: icebox
priority: P1
appetite: 1d
created: 2026-08-11
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-929: Fix the reindex_dispatch SQLite self-deadlock on extractor failure

**Outcome (one sentence):** A task-path .md whose extractor raises no longer leaves the prune write transaction open, so the next connection does not busy-wait forever.

## Read First
- src/core/graph_os/tools/reindex_dispatch.py
- src/core/graph_os/backends/_sqlite_connection.py

## Repro Steps
1. (fill in: exact steps to reproduce)
2. ...
Expected: ...
Actual: ...

## Acceptance (G/W/T) — *this IS the Definition of Done*
Given a task .md whose extractor raises ImportError When dispatch runs Then the write transaction is rolled back and a subsequent dispatch on the same DB completes without blocking.

## Work Log
