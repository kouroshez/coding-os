---
id: TASK-302
title: "Graph coverage quick wins: file_index_state GC + symlink/read-error visibility + grammar-drift test"
swimlane: core
kind: feature
epic: graph-coverage-hardening
labels: [ready]
status: archive
priority: P1
appetite: 1d
created: 2026-06-09
started: 2026-06-09
completed: 2026-06-09
agent_session: ses-claude-20260608-203030-6c0f
depends_on: []
blocked_by: []
references: []
---
# TASK-302: Graph coverage quick wins: file_index_state GC + symlink/read-error visibility + grammar-drift test

**Outcome (one sentence):** cos_graph_doctor over-counts (stale file_index_state rows for now-gitignored/deleted files) and symlink/read-error skips are silent; reconcile file_index_state + graph_nodes to the current full walk so the doctor is exact, surface symlink/read-error skip counts like oversize, and add a grammar-drift test guarding code_generic._LANG_SPEC node types.

## Read First
- src/cli/graph_commands.py
- src/core/graph_os/ingest/base.py
- src/core/graph_os/tools/graph.py
- src/core/graph_os/extractors/code_generic.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** file_index_state has rows for paths not in the current FULL walk (gitignored-now or deleted), **When** a full `cos graph-reindex` runs, **Then** those rows AND their graph_nodes are reconciled away, so cos_graph_doctor's parse-error and stale-path counts reflect only currently-indexed files (no over-count). Single-file/incremental dispatch must NOT trigger this GC.
- **Given** the walk skips symlinks and unreadable files, **When** the reindex summary prints, **Then** their counts are surfaced like oversized files (no longer silent).
- **Given** a tree-sitter grammar could rename node types, **When** the grammar-drift test runs, **Then** it fails if any _LANG_SPEC func/class node type for an installed grammar (rust, ruby) no longer appears when parsing a known sample.
- **Then** graph_os matrix green; doctor parse-error count == this-run reindex count after a full force run.

## Work Log
- 2026-06-09 [claude]: file_index_state+nodes+edges reconciled to the current full walk (pruned 33 stale now-gitignored/deleted files, 247 node
- 2026-06-09 [claude]: committed d3a5d638: src/cli/graph_commands.py, src/core/graph_os/ingest/base.py, src/core/graph_os/tests/test_code_gener
