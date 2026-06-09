---
id: TASK-279
title: "Wave 1: persist graph_node embeddings so cos_graph_similar reads stored vectors"
swimlane: "graph_os"
kind: feature
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-09
started: 2026-06-08
completed: 2026-06-08
agent_session: ses-claude-20260608-203030-6c0f
depends_on: []
blocked_by: []
references: []
---
# TASK-279: Wave 1: persist graph_node embeddings so cos_graph_similar reads stored vectors

**Outcome (one sentence):** cos_graph_similar drops from measured 1806ms to ~10ms by reading persisted graph_node vectors (source_table='graph_nodes') instead of encoding ~200 candidates per call; full candidate pool removes window-bias; graceful fallback to on-the-fly when vectors absent; green tests.

## Read First
- src/core/thinking_os/embeddings.py
- src/core/graph_os/tools/graph.py
- src/core/thinking_os/database.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a DB whose graph_nodes have persisted embeddings (source_table='graph_nodes')
- **When** cos_graph_similar(uid) is called on a node with a stored vector
- **Then** it ranks candidates from persisted vectors (no per-candidate encode), returns correct top_k, median latency <100ms (vs 1806ms baseline); falls back to on-the-fly when no vectors exist; reindex_all populates graph_nodes embeddings for function/method/class/route/mcp_tool/doc_heading; all new + existing graph_os and embeddings tests green.

## Work Log
- 2026-06-09 [claude]: DONE. Persisted graph_node embeddings (reindex_all now embeds function/method/class/route/mcp_tool/doc_heading kinds; 83
- 2026-06-09 [claude]: committed 4fdf0d72: docs/engineering/graph_os-queries.md, src/core/graph_os/tests/test_mcp_tools.py, src/core/graph_os/t
