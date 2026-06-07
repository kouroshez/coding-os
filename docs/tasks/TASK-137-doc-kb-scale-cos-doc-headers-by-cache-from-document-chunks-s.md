---
id: TASK-137
title: "doc-KB scale — cos_doc_headers_by cache from document_chunks + sort-before-truncate + FTS-only beginner flag"
swimlane: thinking_os
kind: refactor
epic: doc-system
labels: [docs-system, performance, rag, audit-d7-f6, ready]
status: complete
priority: P2
appetite: "1d"
created: 2026-06-05
started: 2026-06-06
completed: 2026-06-06
agent_session: ses-claude-20260527-151803-0b9f
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
- **Given** the doc-KB and cos_doc_search at HEAD
- **When** cos_doc_search runs (with or without the rag embedding extra) and list_doc_headers returns a filtered set
- **Then** cos_doc_search meta carries `retrieval_mode='lexical-only'` when embeddings are unavailable and the requested mode otherwise (D7-F4), and list_doc_headers sorts by priority/recency before truncating (D7-F5).

### D7-F6 — intentionally NOT done (mis-spec, would regress correctness)
Reading headers from `document_chunks` instead of the FS walk was rejected: the table indexes only **RAG-source** docs (78 of 95 `docs/**.md` at HEAD), so a DB-backed scan would silently drop ~30 on-disk headers (`00-index.md`, `_meta/`, `audits/`). `cos_doc_headers_by` must return every header under a root, so the bounded **3 KB/file** FS walk is correct and negligible at realistic doc counts. Decision recorded here rather than shipping a subtle data-loss bug. Re-spec needed (e.g. index ALL docs, or an mtime-keyed parse cache) before any DB-backed scan.

Verification: thinking_os suite 1337 passed + doc subset 142 passed, MCP self-test exit 0, `retrieval_mode` present in the live cos_doc_search envelope.

## Work Log
- 2026-06-06 [claude]: Status transitioned to complete via cos task-done.
- 2026-06-06 [claude]: committed 41bf269e: src/core/thinking_os/server.py
