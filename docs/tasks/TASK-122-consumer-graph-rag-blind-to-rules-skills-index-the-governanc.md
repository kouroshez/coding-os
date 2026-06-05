---
id: TASK-122
title: "Consumer graph + RAG blind to rules/skills — index the governance layer (symlink-resolve in walk + RAG sources)"
swimlane: graph_os
kind: bug
epic: doc-system
labels: [docs-system, dogfood, graph, rag, critical, audit-d3-f2, ready]
status: icebox
priority: P0
appetite: "1d"
created: 2026-06-05
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-122: Consumer graph + RAG blind to rules/skills — index the governance layer (symlink-resolve in walk + RAG sources)

**Outcome (one sentence):** In a consumer project, cos_graph_* and cos_doc_search return >0 rule/skill nodes. Fix the graph walk to resolve .md symlinks pointing outside the root (base.py:158 skips symlinks; .claude/ is also folder-excluded at :140) AND add src/core/rules + skills as RAG sources, so graph-first discipline (enforce-graph-context, rename-plan) and semantic discovery can see the governance they enforce. Add a consumer-project test asserting rule nodes > 0 after reindex.

## Read First
- docs/tasks/audits/audit-doc-system-2026-06-05.md
- src/core/graph_os/ingest/base.py
- src/templates/_base/scaffold/.coding-os/rag-config.yaml
- src/core/scripts/install-adapter.sh

## Repro Steps
1. (fill in: exact steps to reproduce)
2. ...
Expected: ...
Actual: ...

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** ...
- **When** ...
- **Then** ...

## Work Log
