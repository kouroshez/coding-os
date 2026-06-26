---
id: TASK-017
title: "fix prune_deleted_path missing PRAGMA foreign_keys ON"
swimlane: graph_os
kind: bug
epic: null
labels: [graph, dangling-edges, sqlite-fk]
status: archive
priority: P1
appetite: "1h"
created: 2026-05-23
started: 2026-05-23
completed: 2026-05-23
agent_session: ses-claude-20260523-010526-e647
depends_on: []
blocked_by: []
references:
  - src/scripts/prune_deleted_path.py
  - src/core/graph_os/backends/sqlite_backend.py
  - src/core/hooks/auto-prune-deleted-files.sh
---
# TASK-017: fix prune_deleted_path missing PRAGMA foreign_keys ON

**Outcome (one sentence):** Deleting a file no longer leaks orphan `graph_edges_v12` rows — the prune helper enables FK enforcement so `ON DELETE CASCADE` actually fires, draining the 20.5 k `dangling_source` issue at its source.

## Read First
- [src/scripts/prune_deleted_path.py](../../src/scripts/prune_deleted_path.py) — the bug (line 37 opens connection without PRAGMA)
- [src/core/graph_os/backends/sqlite_backend.py](../../src/core/graph_os/backends/sqlite_backend.py) — reference connection bootstrap (does enable `foreign_keys = ON`, lines 84 + 91)
- [src/core/hooks/auto-graph-reconcile-shell.sh](../../src/core/hooks/auto-graph-reconcile-shell.sh) (formerly `auto-prune-deleted-files.sh`) — PostToolUse Bash hook that invokes the script after every `rm`/`git mv`

## Repro Steps
1. Pick any indexed file. Capture baseline: `sqlite3 .coding-os/coding-os.db "SELECT COUNT(*) FROM graph_edges_v12 e LEFT JOIN graph_nodes n ON n.id=e.source_id WHERE n.id IS NULL;"`.
2. Run a deletion-equivalent through the prune helper: `python src/scripts/prune_deleted_path.py --force <indexed-path>`.
3. Re-run the dangling-source count from step 1.

Expected: count unchanged because `ON DELETE CASCADE` removed every dependent edge. Actual: count grows by N (where N = previous out-edges of the deleted node), because `sqlite3.connect()` defaults to `PRAGMA foreign_keys = OFF` so the declared CASCADE is silently skipped.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a node with N outgoing edges in `graph_edges_v12`
- **When** `prune_deleted_path._prune_one()` deletes that node
- **Then** all N edges are also removed in the same transaction (verified row-count delta), `uv run --extra graph_os pytest src/core/graph_os/tests/ -q` stays green, and after `cos_graph_doctor(fix=True)` drains historical orphans the doctor `dangling_source` count returns 0 on subsequent invocations.

## Work Log
- 2026-05-23 — diagnosed via Wave-1 audit + direct schema check: `graph_edges_v12` declares FK with `ON DELETE CASCADE`, `SqliteBackend.__init__` sets `PRAGMA foreign_keys = ON` but the peer `src/scripts/prune_deleted_path.py` opens its own connection without the PRAGMA → CASCADE silently skipped on every PostToolUse Bash deletion. Reproduced behavior with a 5-line fixture (no-PRAGMA: edges orphan; PRAGMA-on: CASCADE fires). Added one-line `conn.execute("PRAGMA foreign_keys = ON")` + comment. graph_os matrix suite (642 passed, 16 skipped) clean.
- 2026-05-23 [claude]: Status transitioned to complete via cos task-done.
