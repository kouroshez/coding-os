---
id: TASK-040
title: "graph ranking: strengthen query-personalization relevance (F6)"
swimlane: infra
kind: chore
epic: null
labels: [ready]
status: complete
priority: P3
appetite: "1d"
created: 2026-05-29
started: null
completed: 2026-05-29
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---

# TASK-040: graph ranking: strengthen query-personalization relevance (F6)

**Outcome (one sentence):** cos_graph_ranking(query=...) returns query-relevant nodes, not generic PageRank hubs; backed by a relevance eval fixture.

## Work Log
- 2026-05-29 [claude]: DONE (commit 4bc385f): F6 ranking relevance fixed. Query personalization seeded ANY node whose uid PATH contained a quer
