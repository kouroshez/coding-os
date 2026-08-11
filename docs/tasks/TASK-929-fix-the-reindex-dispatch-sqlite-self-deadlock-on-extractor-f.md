---
id: TASK-929
title: "Fix the reindex_dispatch SQLite self-deadlock on extractor failure"
swimlane: "graph_os"
kind: bug
epic: null
labels: [ready]
status: complete
priority: P1
appetite: 1d
created: 2026-08-11
started: 2026-08-11
completed: 2026-08-11
agent_session: ses-claude-20260807-224955-abc1
depends_on: []
blocked_by: []
references: []
---
# TASK-929: Fix the reindex_dispatch SQLite self-deadlock on extractor failure

**Outcome (one sentence):** A write that raises mid-statement rolls its transaction back, so the thread-cached connection never strands an open transaction that blocks every other connection with "database is locked".

## Read First
- src/core/graph_os/backends/_sqlite_write.py
- src/core/graph_os/tools/_reindex_layers.py

## Repro Steps
1. Open a backend on a fresh DB via the dispatcher's `_open_conn` pragmas.
2. Call `backend.upsert_node(node)` with a node whose `label` is not a SQLite-bindable type, so `execute()` raises after the implicit transaction has begun.
3. Read `conn.in_transaction`, then write from an independent `sqlite3.connect(db, timeout=2.0)`.

Expected: `in_transaction is False` and the second connection writes.
Actual: `in_transaction is True` and the second connection raises `OperationalError: database is locked`.

Note: the original card blamed the prune transaction. That is wrong — `delete_nodes_for_file` commits. The real gap is that `upsert_node`, `delete_node` and `delete_nodes_for_file` took the write lock without the rollback-on-failure that `upsert_edge` already had; releasing the in-process lock does not end the SQLite transaction.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a backend write that raises mid-statement
- **When** the exception propagates out of the write method
- **Then** the transaction is rolled back, `conn.in_transaction` is False, and a subsequent dispatch on the same DB completes without blocking.

## Work Log
- 2026-08-11 [claude]: Edit probe_deadlock.py
- 2026-08-11 [claude]: Edit probe_deadlock2.py
- 2026-08-11 [claude]: Edit _sqlite_write.py
- 2026-08-11 [claude]: Edit _sqlite_write.py
- 2026-08-11 [claude]: Edit _sqlite_write.py
- 2026-08-11 [claude]: Edit _sqlite_write.py
- 2026-08-11 [claude]: Edit _sqlite_write.py
- 2026-08-11 [claude]: Edit test_sqlite_write_rollback.py
- 2026-08-11 [claude]: Edit test_sqlite_write_rollback.py
- 2026-08-11 [claude]: Edit test_sqlite_write_rollback.py
- 2026-08-11 [claude]: commit 028196bf3d — fix(graph_os): roll back the write transaction when a backend statement raises
- 2026-08-11 [claude]: Status transitioned to complete via cos task-done.
