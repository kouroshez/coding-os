---
id: TASK-123
title: "Fix RAG source allocation — adr phantom path, unindexed adapters/design/content, drop RN override dup"
swimlane: thinking_os
kind: bug
epic: doc-system
labels: [docs-system, rag, dogfood, audit-d3-f3, ready]
status: icebox
priority: P1
appetite: "1d"
created: 2026-06-05
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-123: Fix RAG source allocation — adr phantom path, unindexed adapters/design/content, drop RN override dup

**Outcome (one sentence):** rag-config.yaml (base scaffold + meta) indexes the docs that actually exist: docs/adr/ instead of the phantom docs/architecture/adr/ (6 ADRs currently unindexed everywhere), docs/adapters/, and the design/ + pages-content-spec/ sources moved into base so nextjs design tokens + content spec are retrievable via cos_doc_search; the drift-prone react-native override is removed. Golden fixtures regenerated.

## Read First
- docs/tasks/audits/audit-doc-system-2026-06-05.md
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
