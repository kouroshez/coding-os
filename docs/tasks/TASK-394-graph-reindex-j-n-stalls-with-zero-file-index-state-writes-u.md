---
id: TASK-394
title: "graph-reindex -j N stalls with zero file_index_state writes under a live MCP server"
swimlane: "graph_os"
kind: bug
epic: null
labels: [graph-os, reindex, concurrency, ready]
status: complete
priority: P3
appetite: 4h
created: 2026-06-11
started: 2026-06-11
completed: 2026-06-11
agent_session: ses-claude-20260610-185418-2b3f
depends_on: []
blocked_by: []
references: []
---

# TASK-394: graph-reindex -j N stalls with zero file_index_state writes under a live MCP server

**Outcome (one sentence):** Root-cause and fix the stall observed 2026-06-11: `cos graph-reindex --path docs/tasks --force --no-docs -j 4` spawned 23 worker processes that wrote zero file_index_state rows for 15+ minutes (parent CPU 0.22s) while the coding-os MCP server held a connection to the same SQLite DB; run completes or fails loudly instead of hanging silently.

## Read First
- src/core/graph_os/tools/reindex_dispatch.py
- src/core/graph_os/backends/sqlite_backend.py
- docs/tasks/TASK-393-graph-hygiene-extractor-stub-minting-fixes-reindex-symbol-pr.md

## Repro Steps
1. With the coding-os MCP server running (hub + a live agent session holding the SQLite connection), run `cos graph-reindex --path docs/tasks --force --no-docs -j 4` in the meta-repo (~830 task files).
2. Watch `SELECT MAX(last_indexed_at) FROM file_index_state WHERE file_path LIKE 'docs/tasks/%'` — observed frozen for 15+ min while 23 worker processes stayed alive with near-zero CPU.
Expected: steady row writes (~100ms/file) and a completion summary; on lock contention, bounded retry then loud failure.
Actual: silent indefinite stall; run had to be killed (single-file dispatch through the same code path worked fine, ~100ms/file).

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a live MCP server connected to the project DB, **When** `cos graph-reindex --force -j 4` runs over docs/tasks, **Then** it completes with per-file rows written, or aborts loudly within a bounded lock-wait — never a silent multi-minute hang.
- **Given** the root cause is identified, **When** the fix lands, **Then** a regression test (or documented manual probe) covers the parallel-writer + long-lived-reader scenario.

## Work Log
- 2026-06-11 [claude]: Root-caused under TASK-395. Three stacked mechanisms: (1) CLI counted per-file graph-layer write failures as PROCESSED (
- 2026-06-11 [claude]: Status transitioned to complete via cos task-done.
- 2026-06-11 [claude]: committed 8b6ea66a: docs/engineering/mcp-error-envelope.md, docs/playbooks/polyglot-extractor-roadmap.md, src/cli/graph_
