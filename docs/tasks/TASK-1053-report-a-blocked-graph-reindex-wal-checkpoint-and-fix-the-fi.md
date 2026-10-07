---
id: TASK-1053
title: "Report a blocked graph-reindex WAL checkpoint and fix the final review's findings"
swimlane: "graph_os"
kind: bug
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-10-07
started: 2026-10-07
completed: 2026-10-07
agent_session: ses-claude-20261004-231430-d18a
depends_on: []
blocked_by: []
references: []
---
# TASK-1053: Report a blocked graph-reindex WAL checkpoint and fix the final review's findings

**Outcome (one sentence):** A periodic `graph-reindex -j` WAL checkpoint that a reader blocks gives up within seconds and says so, and every confirmed finding of the final read-only review of the TASK-1051 commits is fixed with a test.

## Read First
- [docs/engineering/graph-os-polyglot-audit-2026-10-07-final-round.md § Write path under load](../engineering/graph-os-polyglot-audit-2026-10-07-final-round.md#write-path-under-load)
- `src/cli/_graph_cli_shared.py::wal_checkpoint`, `src/core/hooks/_helpers/wal_guard.py::_checkpoint_truncate`

## Repro Steps
1. Open a read transaction on the graph DB and hold it, then commit a write from another connection.
2. Call `wal_checkpoint(project_root)` as the parallel reindex loop does every 100 files.
Expected: it returns within a few seconds and prints a `[WARN]` naming the blocked checkpoint.
Actual: it waits up to 30 s (blocking the workers' writes meanwhile, per sqlite.org/pragma.html) and ignores the busy column, so a starved checkpoint is silent.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a reader pinning an old snapshot **When** `wal_checkpoint` runs **Then** it returns within the busy timeout and stderr carries `[WARN]` and `busy`.
- **Given** no reader **When** `wal_checkpoint` runs **Then** the WAL file is truncated to 0 bytes and nothing is printed.
- **Given** the final review's report **When** each confirmed finding is fixed **Then** it has a regression test and the graph_os, CLI and lint matrix rows are green.

## Work Log
- 2026-10-07 [claude]: Edit TASK-1053-report-a-blocked-graph-reindex-wal-checkpoint-and-fix-the-fi.md
- 2026-10-07 [claude]: Edit graph-os-polyglot-audit-2026-10-07-final-round.md
- 2026-10-07 [claude]: Edit _graph_cli_shared.py
- 2026-10-07 [claude]: Edit test_wal_guard.py
- 2026-10-07 [claude]: commit fe6165b7cc — fix(cli): give up a reader-blocked graph-reindex WAL checkpoint after 3 s and warn about it
- 2026-10-07 [claude]: Edit _graph_fragments.py
- 2026-10-07 [claude]: Edit _graph_fragments.py
- 2026-10-07 [claude]: Edit _graph_fragments.py
- 2026-10-07 [claude]: Edit _graph_fragments.py
- 2026-10-07 [claude]: Edit test_fragment_clones.py
- 2026-10-07 [claude]: Edit _graph_fragments.py
- 2026-10-07 [claude]: commit e0ec05e1fc — fix(graph_os): keep semicolon-free exports, list every back-to-back copy and bound fragment memory
- 2026-10-07 [claude]: W-02 + F-01..F-12 fixed with tests; graph_os 1599 pass, lint green, fragments smoke 1.98 s on a scope
- 2026-10-07 [claude]: Edit mypy-ratchet-local-count-hides-ci.md
- 2026-10-07 [claude]: Status transitioned to complete via cos task-done.
