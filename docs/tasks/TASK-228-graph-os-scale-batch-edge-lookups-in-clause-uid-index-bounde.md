---
id: TASK-228
title: "graph_os scale: batch edge lookups (IN-clause) + uid index + bounded scans + honest truncation in centrality/ranking/export"
swimlane: "graph_os"
kind: feature
epic: enterprise-scale
labels: [scale, graph, performance, ready]
status: complete
priority: P1
appetite: 3d
created: 2026-06-07
started: 2026-06-07
completed: 2026-06-07
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-228: graph_os scale: batch edge lookups (IN-clause) + uid index + bounded scans + honest truncation in centrality/ranking/export

**Outcome (one sentence):** graph_os stays responsive at 100K-1M nodes: per-node list_edges loops in centrality/betweenness become a single batched IN-clause / JOIN; degree_map_for stops the OR-join that bypasses indexes; an index on graph_nodes(uid) backs resolve/lookups; ranking's unbounded edge enumeration is bounded; every coverage tool sets truncated honestly (no silent drop). Verified by a 200K-node graph keeping export/query/centrality under a fixed latency budget.

## Read First
- src/core/graph_os/tools/graph.py
- src/core/graph_os/backends/sqlite_backend.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a 200K-node / ~400K-edge graph.
- **When** centrality/betweenness, ranking, degree computation, query/resolve and export run.
- **Then** per-node list_edges loops are replaced by one batched IN-clause/JOIN; degree_map_for avoids the index-bypassing OR-join; graph_nodes(uid) is indexed; edge scans are bounded; coverage tools set truncated honestly; verified under a fixed latency budget at 200K nodes (no per-node query storm).

## Work Log
- 2026-06-07 [claude]: committed 72cf92c1: src/core/graph_os/tools/graph.py
- 2026-06-07 [claude]: committed 72cf92c1: _degree_map_for OR->UNION; _edges_among chunked indexed batch powers betweenness + ranking (replaced
- 2026-06-07 [claude]: Status transitioned to complete via cos task-done.
