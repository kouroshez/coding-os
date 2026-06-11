---
id: TASK-126
title: "Cross-reference discovery — query-time semantic neighbors in cos_doc_search so an applicable rule elsewhere is surfaced"
swimlane: thinking_os
kind: feature
epic: doc-system
labels: [docs-system, rag, graph, cross-ref, audit-d3-f6, ready]
status: archive
priority: P1
appetite: "1d"
created: 2026-06-05
started: null
completed: null
agent_session: ses-claude-20260527-151803-0b9f
depends_on: [TASK-122]
blocked_by: []
references: []
---
# TASK-126: Cross-reference discovery — query-time semantic neighbors in cos_doc_search so an applicable rule elsewhere is surfaced

**Outcome (one sentence):** Reading doc X surfaces a semantically-related rule/doc the author never explicitly linked: cos_doc_search returns top-k semantic neighbors of each hit's source doc (computed at query time from existing embeddings — NO new persisted edge type, rule-of-three). Depends on TASK-122 so rules/skills are in the embedding space. Closes the user's #1 worry that cross-reference completeness depends on author hand-linking.

## Read First
- src/core/thinking_os/tools/docs.py
- src/core/graph_os/tools/graph.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** ...
- **When** ...
- **Then** ...

## Work Log
- 2026-06-06 [claude]: ARCHIVED (not done) — anti-overengineering (Rule 22). Query-time semantic-neighbor expansion in cos_doc_search is a spec
