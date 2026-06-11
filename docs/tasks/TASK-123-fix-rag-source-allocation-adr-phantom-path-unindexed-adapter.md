---
id: TASK-123
title: "Fix RAG source allocation — adr phantom path, unindexed adapters/design/content, drop RN override dup"
swimlane: thinking_os
kind: bug
epic: doc-system
labels: [docs-system, rag, dogfood, audit-d3-f3, ready]
status: archive
priority: P1
appetite: "1d"
created: 2026-06-05
started: null
completed: null
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-123: Fix RAG source allocation — adr phantom path, unindexed adapters/design/content, drop RN override dup

**Outcome (one sentence):** rag-config.yaml (base scaffold + meta) indexes the docs that actually exist: docs/adr/ instead of the phantom docs/architecture/adr/ (6 ADRs currently unindexed everywhere), docs/adapters/, and the design/ + pages-content-spec/ sources moved into base so nextjs design tokens + content spec are retrievable via cos_doc_search; the drift-prone react-native override is removed. Golden fixtures regenerated.

## Read First
- src/templates/_base/scaffold/.coding-os/rag-config.yaml
- src/core/thinking_os/doc_indexer.py
- docs/adr/

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
- 2026-06-07 [claude]: ARCHIVED — premises verified WRONG (the audit had the ADR path backwards). rag-config points to docs/architecture/adr/ w
