---
id: TASK-124
title: "Reclassify graph rule/skill nodes (kind=doc_file→rule/skill) + surface missing-frontmatter chunk count"
swimlane: graph_os
kind: bug
epic: doc-system
labels: [docs-system, graph, rag, audit-d3-f5, ready]
status: icebox
priority: P2
appetite: "1d"
created: 2026-06-05
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-124: Reclassify graph rule/skill nodes (kind=doc_file→rule/skill) + surface missing-frontmatter chunk count

**Outcome (one sentence):** cos graph-reindex --force re-classifies the 6 rules + 116 skills currently mis-tagged kind=doc_file (content-hash skip never re-ran classification); a determinism test guards classification on re-index; and doc-index reports the count of indexed files with unparseable frontmatter (currently a silent logger.debug) so Stage-1 metadata gaps are visible.

## Read First
- docs/tasks/audits/audit-doc-system-2026-06-05.md
- src/core/graph_os/ingest/base.py
- src/core/thinking_os/doc_indexer.py

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
