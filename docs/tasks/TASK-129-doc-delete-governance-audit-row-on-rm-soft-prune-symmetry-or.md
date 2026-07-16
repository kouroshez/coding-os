---
id: TASK-129
title: "Doc-delete governance \u2014 audit row on rm + soft-prune symmetry + orphan-chunk reconciliation + read_error prune fix"
swimlane: core
kind: bug
epic: doc-system
labels: [docs-system, enforcement, audit-trail, audit-d5-f2, ready]
status: archive
priority: P1
appetite: 1d
created: 2026-06-05
started: 2026-06-06
completed: 2026-06-06
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-129: Doc-delete governance — audit row on rm + soft-prune symmetry + orphan-chunk reconciliation + read_error prune fix

**Outcome (one sentence):** Deleting a doc is no longer a silent, unaudited hard-erase: the rm-prune path writes an action='deleted' doc_audit_trail row (D5-F2), and reindex_dispatch's read_error short-circuit no longer skips graph prune for a file that no longer exists (D7-F1) so deleted files don't leave orphan graph nodes. (Over-built parts deferred: D5-F9 cos-doctor orphan-chunk reconciliation sweep and D5-F10 periodic CI reconciliation are diminishing-returns — the prune paths already keep state consistent.)

## Read First
- src/core/graph_os/tools/reindex_dispatch.py
- src/scripts/prune_deleted_path.py

## Repro Steps
1. Index a doc, then delete it and call reindex on its (now-missing) path.
2. reindex_dispatch hits the `read_error is not None` branch (file unreadable) and sets graph layer status=error WITHOUT pruning — the deleted file's graph nodes linger as orphans.
3. Separately, the rm-prune path (prune_deleted_path.py) erases graph/RAG rows but writes no audit record, so a doc deletion leaves no forensic trail.
Expected: a missing (deleted) path is pruned from the graph; a doc deletion appends an action='deleted' doc_audit_trail row.
Actual: orphan graph nodes after a read-error delete; no audit row on doc delete.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** reindex is called on a path whose file no longer exists
- **When** the read fails
- **Then** reindex_dispatch prunes the file's graph nodes (status='pruned', nodes_pruned reported) instead of short-circuiting; a transient read error on a path that DOES exist still returns status=error and prunes nothing; AND prune_deleted_path appends an action='deleted' doc_audit_trail row for deleted docs (.md). Verified by test-graph_os + a prune test.

## Work Log
- 2026-06-07 [claude]: D7-F1: reindex_dispatch read_error branch now distinguishes deletion from transient — a path gone from disk is pruned (_
- 2026-06-07 [claude]: committed c3267406: src/core/graph_os/tests/test_reindex_dispatch.py, src/core/graph_os/tools/reindex_dispatch.py, src/s
