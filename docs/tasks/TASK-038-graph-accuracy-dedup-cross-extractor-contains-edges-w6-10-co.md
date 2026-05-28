---
id: TASK-038
title: "graph accuracy: dedup cross-extractor contains edges (W6.10) + correct stale-paths false-positive diagnosis"
swimlane: infra
kind: bug
epic: null
labels: [graph_os, accuracy, W6.10]
status: complete
priority: P2
appetite: "1d"
created: 2026-05-28
started: 2026-05-28
completed: 2026-05-28
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-038: graph accuracy: dedup cross-extractor contains edges (W6.10) + correct stale-paths false-positive diagnosis

**Outcome (one sentence):** Centrality in/out-degree no longer inflated by 703 duplicate folder-spine `contains` rows; doctor stale_paths diagnosis corrected (rendered-location relative-link false-positives, not doc-debt).

## Read First
- docs/engineering/graph-os-round3-fix-checklist-2026-05-26.md
- src/core/graph_os/backends/sqlite_backend.py
- src/core/graph_os/tools/graph.py

## Repro Steps
1. Query the live graph DB: `SELECT edge_type, SUM(n-1) FROM (SELECT edge_type, COUNT(*) n FROM graph_edges_v12 GROUP BY source_id,target_id,edge_type HAVING n>1) GROUP BY edge_type`.
2. Observe 703 redundant rows, all `contains` (folder-spine emitted once per extractor; a file touched by ≥2 extractors gets N folder→file rows differing only by `extractor`).
3. `cos_graph_centrality(by="degree")` uses `COUNT(e.id)` (not DISTINCT) → folder/file in/out-degree inflated by the duplicates.
Expected: one `contains` edge per (folder,file) pair; centrality degree counts each structural link once.
Actual: up to N rows per pair; folder centrality artificially inflated.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a file processed by ≥2 extractors (e.g. a task `.md` via md_links + task_deps)
- **When** the graph is reindexed and `cos_graph_doctor(fix=True)` then `cos_graph_centrality` run
- **Then** the (folder→file) `contains` edge exists exactly once, doctor reports 0 cross-extractor `contains` duplicates, centrality in/out-degree drops for affected folders, and graph_os tests stay green.

## Work Log
- 2026-05-28 [claude]: A1 `upsert_edge` dedups `contains` ignoring `extractor`; A2 `cos_graph_doctor` adds `duplicate_contains` detect+fix. Verified: doctor reported 703 redundant (629 pairs) → fix → 0; `folder:tests` out-degree 148→74; +2 backend regression tests; `graph_os` suite 698 passed. B1 corrected the round-4 stale-paths false-positive diagnosis. Stale-paths root fix (render-location-aware resolver) deferred — needs design judgment (Rule 22).
- 2026-05-28 [claude]: Status transitioned to complete via cos task-done.
