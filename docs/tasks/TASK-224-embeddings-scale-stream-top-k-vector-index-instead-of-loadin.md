---
id: TASK-224
title: "Embeddings scale: stream top-K / vector index instead of loading all embeddings; batch reindex_all"
swimlane: "thinking_os"
kind: feature
epic: enterprise-scale
labels: [scale, embeddings, rag, memory, ready]
status: archive
priority: P0
appetite: 3d
created: 2026-06-07
started: 2026-06-07
completed: 2026-06-07
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-224: Embeddings scale: stream top-K / vector index instead of loading all embeddings; batch reindex_all

**Outcome (one sentence):** search_similar() no longer loads ALL embeddings into memory (1.5GB+ at 1M rows): use a vector index (sqlite-vec/FAISS) or a chunked streaming top-K heap with bounded memory; reindex_all() batches via embed_texts (32-64) instead of per-row upsert. Verified by a 1M-embedding search staying under a fixed memory ceiling.

## Read First
- src/core/thinking_os/embeddings.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** ~1M rows in the embeddings table.
- **When** search_similar(query) and reindex_all() run.
- **Then** search uses a vector index OR a chunked streaming top-K heap with a bounded memory ceiling (no fetchall of all vectors into RAM), and reindex_all batches via embed_texts; verified by a 1M-embedding search + full reindex staying under a fixed memory ceiling and acceptable latency.

## Work Log
- 2026-06-07 [claude]: committed 733a05d2: src/core/thinking_os/embeddings.py
- 2026-06-07 [claude]: committed 733a05d2: search_similar streams 4096-row batches into a top-K heap (bounded memory, exact match to brute-forc
- 2026-06-07 [claude]: Status transitioned to complete via cos task-done.
