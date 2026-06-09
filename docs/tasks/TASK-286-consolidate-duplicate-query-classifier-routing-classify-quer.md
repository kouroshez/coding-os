---
id: TASK-286
title: "Consolidate duplicate query classifier (routing.classify_query vs retrieve._classify_query_shape)"
swimlane: "thinking_os"
kind: refactor
epic: retrieval-routing-fix
labels: [routing, drift, ssot, ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-09
started: 2026-06-09
completed: 2026-06-09
agent_session: ses-claude-20260609-143642-c7c5
depends_on: []
blocked_by: []
references: []
---
# TASK-286: Consolidate duplicate query classifier (routing.classify_query vs retrieve._classify_query_shape)

**Outcome (one sentence):** Two divergent query classifiers exist: routing.classify_query (L285, buckets ~everything "conceptual" — proven to misroute "who calls X" and "rename X") and retrieve._classify_query_shape (L222). Map all consumers via cos_graph_references first. Consolidate to one classifier or clearly separate responsibilities (shape-for-logging vs intent-for-routing), removing the drift. If classify_query has no remaining consumer after the A1 purge, remove it (defer-by-default). Fix or delete with error handling; no silent dead code.

## Read First
- src/core/thinking_os/tools/routing.py
- src/core/thinking_os/tools/retrieve.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** two divergent classifiers — routing.classify_query (intent) and retrieve._classify_query_shape (logging shape) — with overlapping responsibility.
- **When** all consumers are mapped via cos_graph_references and the duplication is resolved (one classifier, or cleanly separated roles with distinct names).
- **Then** no orphaned/dead classifier remains, any removal is justified by zero live consumers, error paths are explicit (no silent fall-through), and `uv run --extra rag pytest src/core/thinking_os/tests/ -q` is green.

## Work Log
- 2026-06-09 [claude]: Graph proved classify_query had 7 refs ALL from test_routing.py (zero production consumers — built for the never-wired c
