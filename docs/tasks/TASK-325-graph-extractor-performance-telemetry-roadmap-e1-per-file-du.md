---
id: TASK-325
title: "Graph extractor performance telemetry (roadmap E1) \u2014 per-file duration_ms in file_index_state + doctor/hub surface"
swimlane: "graph_os"
kind: feature
epic: null
labels: [graph, observability, audit-2026-06-09, ready]
status: complete
priority: P3
appetite: 1d
created: 2026-06-10
started: 2026-06-10
completed: 2026-06-10
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-325: Graph extractor performance telemetry (roadmap E1) — per-file duration_ms in file_index_state + doctor/hub surface

**Outcome (one sentence):** Each reindex records per-extractor duration_ms into file_index_state (append-only migration, Rule 9), cos_graph_doctor reports the slowest extractors/files, and the polyglot roadmap E1 row flips to shipped — budget data exists before the next monorepo-scale consumer hits a slow wall.

## Read First
- docs/playbooks/polyglot-extractor-roadmap.md (E1 scope — the spec)
- src/core/graph_os/tools/reindex_dispatch.py (timing capture point)
- src/core/thinking_os/database.py (vN+1 migration — append-only)
- src/core/graph_os/backends/sqlite_backend.py (file_index_state writes)

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a reindex of any file
- **When** dispatch completes
- **Then** file_index_state carries duration_ms for that run (new column via vN+1 migration, no past-migration edits)
- **Given** cos_graph_doctor
- **When** it runs after several reindexes
- **Then** it reports the top-N slowest extractors/files as an informational category
- **Given** the graph_os verification matrix
- **When** `uv run --extra graph_os pytest src/core/graph_os/tests/ -q` runs
- **Then** green, including a new timing-capture test

## Work Log
- 2026-06-10 [claude]: Shipped (score 9/10). Rule-18 reconcile mid-task: E1.1 (duration_ms column, migration v28 + write site) was ALREADY ship
- 2026-06-10 [claude]: committed a7c0f0ef: docs/playbooks/polyglot-extractor-roadmap.md, src/core/graph_os/tests/test_centrality_ranking_doctor
- 2026-06-10 [claude]: Status transitioned to complete via cos task-done.
