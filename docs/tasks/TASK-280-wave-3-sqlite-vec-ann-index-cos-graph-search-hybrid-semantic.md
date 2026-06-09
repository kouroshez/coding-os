---
id: TASK-280
title: "Wave 3: sqlite-vec ANN index + cos_graph_search hybrid (semantic+FTS5+centrality)"
swimlane: "graph_os"
kind: feature
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-09
started: 2026-06-09
completed: 2026-06-09
agent_session: ses-claude-20260608-203030-6c0f
depends_on: []
blocked_by: []
references: []
---
# TASK-280: Wave 3: sqlite-vec ANN index + cos_graph_search hybrid (semantic+FTS5+centrality)

**Outcome (one sentence):** Sublinear ANN search via sqlite-vec vec0 so semantic search stays fast at thousands-x scale; cos_graph_search(query) hybrid re-ranks semantic + FTS5 + centrality; brute-force fallback when the extension is unavailable; measured + green tests.

## Read First
- src/core/thinking_os/embeddings.py
- src/core/graph_os/tools/graph.py
- src/core/thinking_os/database.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** graph_node embeddings exist and the sqlite-vec extension loads
- **When** a semantic kNN over the graph_node pool is issued
- **Then** it uses the vec0 ANN index (sublinear), returns the same top-k as brute force on a small fixture, and transparently falls back to the streaming brute-force scan when the extension is absent; cos_graph_search(query) returns a hybrid-ranked envelope (ok/fail, meta.layer=graph); sqlite-vec is a declared dependency; new + existing tests green.

## Work Log
- 2026-06-09 [claude]: DONE. sqlite-vec vec0 ANN index (graph_os/vec_index.py): sublinear kNN over graph_node embeddings, unit-norm L2->cosine,
