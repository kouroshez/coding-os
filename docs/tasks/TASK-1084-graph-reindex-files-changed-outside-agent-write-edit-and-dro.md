---
id: TASK-1084
title: "Graph: reindex files changed outside agent Write/Edit and drop zero-edge stubs, in-process and bounded"
swimlane: "graph_os"
kind: bug
epic: null
labels: [ready]
status: icebox
priority: P2
appetite: 1d
created: 2026-10-25
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-1084: Graph: reindex files changed outside agent Write/Edit and drop zero-edge stubs, in-process and bounded

**Outcome (one sentence):** The graph stops serving deleted or rewritten code after edits made by scripts, sed -i, heredocs or Codex apply_patch, and zero-edge stub nodes no longer accumulate between doctor runs — without any detached or forked reindex worker.

## Read First
- docs/engineering/graph_os-queries.md
- src/core/hooks/auto-reindex-graph.sh
- src/core/hooks/_reindex_on_edit.sh
- src/core/graph_os/tools/_doctor_orphans.py

## Repro Steps
tests/test_cognition_routes.py was rewritten by a python script at 23:40:31 but the graph kept the 23:39:53 extraction, so context served 11 deleted tests; phantom nodes rose 49 -> 53 and unresolved stubs 398 -> 517 in one afternoon because only doctor fix=true deletes zero-edge stubs. The earlier session-start catch-up was reverted because it forked a detached worker that helped crash the machine.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a file changed by a non-Write/Edit path, **When** a graph tool serves a node from it, **Then** that file is re-extracted inline (single file, bounded time) before answering, or the answer carries stale=true.
- **Given** a reindex pass, **When** it finishes, **Then** stub nodes left with zero edges are deleted in the same process.
- **Given** a Codex apply_patch edit, **When** the post-edit dispatcher runs, **Then** the edited files are reindexed like a Claude Write/Edit.

## Work Log
