---
id: TASK-282
title: "Wave 5: usearch HNSW backend for true sublinear ANN at million-vector scale"
swimlane: "graph_os"
kind: feature
epic: null
labels: [ready]
status: in_progress
priority: P2
appetite: 1d
created: 2026-06-09
started: 2026-06-09
completed: null
agent_session: ses-claude-20260608-203030-6c0f
depends_on: []
blocked_by: []
references: []
---
# TASK-282: Wave 5: usearch HNSW backend for true sublinear ANN at million-vector scale

**Outcome (one sentence):** vec_index gains a usearch HNSW backend (O(log N) query) preferred over the sqlite-vec flat scan and brute-force; benchmark proves sublinear scaling to 1M vectors; same knn() contract + fallback chain; green tests.

## Read First
- src/core/graph_os/vec_index.py
- src/core/graph_os/tools/graph.py
- pyproject.toml

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** graph_node embeddings and usearch installed
- **When** a kNN query runs
- **Then** vec_index uses the HNSW index (query time grows sub-linearly — measured ~flat from 100k→1M while brute grows ~10x), with the same knn() return contract, falling back to sqlite-vec flat then brute force when usearch is absent; the HNSW index is a derived cache rebuilt from the embeddings table; usearch declared in pyproject; new + existing tests green.

## Work Log
