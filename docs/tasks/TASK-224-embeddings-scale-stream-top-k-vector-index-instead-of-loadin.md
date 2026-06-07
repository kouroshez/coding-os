---
id: TASK-224
title: "Embeddings scale: stream top-K / vector index instead of loading all embeddings; batch reindex_all"
swimlane: "thinking_os"
kind: feature
epic: enterprise-scale
labels: [scale, embeddings, rag, memory]
status: icebox
priority: P0
appetite: 3d
created: 2026-06-07
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-224: Embeddings scale: stream top-K / vector index instead of loading all embeddings; batch reindex_all

**Outcome (one sentence):** search_similar() no longer loads ALL embeddings into memory (1.5GB+ at 1M rows): use a vector index (sqlite-vec/FAISS) or a chunked streaming top-K heap with bounded memory; reindex_all() batches via embed_texts (32-64) instead of per-row upsert. Verified by a 1M-embedding search staying under a fixed memory ceiling. See audit-enterprise-scale-2026-06-07.md (rag_embed findings, embeddings.py:456-464,545).

## Read First
- docs/tasks/audits/audit-enterprise-scale-2026-06-07.md
- src/core/thinking_os/embeddings.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** ...
- **When** ...
- **Then** ...

## Work Log
