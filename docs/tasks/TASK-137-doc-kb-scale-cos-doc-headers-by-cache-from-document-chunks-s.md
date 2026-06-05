---
id: TASK-137
title: "doc-KB scale — cos_doc_headers_by cache from document_chunks + sort-before-truncate + FTS-only beginner flag"
swimlane: thinking_os
kind: refactor
epic: doc-system
labels: [docs-system, performance, rag, audit-d7-f6, ready]
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

# TASK-137: doc-KB scale — cos_doc_headers_by cache from document_chunks + sort-before-truncate + FTS-only beginner flag

**Outcome (one sentence):** The doc-KB stays fast + honest at 500+ docs: cos_doc_headers_by reads persisted frontmatter from document_chunks instead of an unbounded per-call FS walk (D7-F6); list_doc_headers sorts by priority BEFORE truncating to limit (D7-F5); and cos_doc_search sets meta.retrieval_mode='lexical-only' when the rag embedding extra is unavailable so the beginner persona is warned, not silently degraded (D7-F4).

## Read First
- docs/tasks/audits/audit-doc-system-2026-06-05.md
- src/core/thinking_os/tools/docs.py
- src/core/thinking_os/doc_indexer.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** ...
- **When** ...
- **Then** ...

## Work Log
