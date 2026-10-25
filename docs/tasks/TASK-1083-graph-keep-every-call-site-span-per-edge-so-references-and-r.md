---
id: TASK-1083
title: "Graph: keep every call-site span per edge so references and rename_plan list all sites"
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

# TASK-1083: Graph: keep every call-site span per edge so references and rename_plan list all sites

**Outcome (one sentence):** A function that calls another N times yields N rename sites: rename_plan and references stop silently dropping the second and later call sites of the same caller.

## Read First
- docs/engineering/graph_os-queries.md
- src/core/graph_os/backends/_sqlite_write.py
- src/core/thinking_os/database.py

## Repro Steps
references(_graph_lookup.py::_resolve_uid, kinds=calls) returns 9 while rg finds 10: _graph_paths.py:201 is missing because :204 in the same caller already holds the one edge; rename_plan(RefactorPanel.tsx::RenamePlanSection) lists RefactorPanel.test.tsx:52 but not :33. graph_edges_v12 is UNIQUE(source_id, target_id, edge_type, extractor) with a single source_span.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a caller with two calls to one function, **When** it is extracted, **Then** both spans are stored (append-only migration, never editing a past one) and rename_plan lists both lines.
- **Given** the edge uniqueness, **When** the file is re-extracted, **Then** spans are replaced, not accumulated, and edge counts are unchanged.

## Work Log
