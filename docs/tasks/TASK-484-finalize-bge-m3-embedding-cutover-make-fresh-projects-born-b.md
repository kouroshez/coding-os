---
id: TASK-484
title: "Finalize BGE-M3 embedding cutover: make fresh projects born BGE-M3 and recalibrate search thresholds"
swimlane: "thinking_os"
kind: feature
epic: null
labels: [embeddings, pre-launch, ready]
status: icebox
priority: P2
appetite: 1d
created: 2026-06-20
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-484: Finalize BGE-M3 embedding cutover: make fresh projects born BGE-M3 and recalibrate search thresholds

**Outcome (one sentence):** Fresh consumer projects are born on BAAI/bge-m3 instead of all-MiniLM-L6-v2, so semantic retrieval (cos_graph_similar, cos_search, cos_doc_search, cos_graph_ranking) separates related vs unrelated far better and is multilingual — done now because zero installed base is the cheapest moment to flip a permanent per-consumer default.

## Read First
- src/core/thinking_os/embeddings.py
- src/core/thinking_os/database.py
- src/core/thinking_os/server.py
- src/core/thinking_os/tools/docs.py
- Makefile

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** the dual-model machinery is already built and tested (per-row model_name/embedding_dim columns, active_model_name SSOT, make migrate-embeddings, calibrated floors MiniLM 0.25 / BGE-M3 0.60), **When** the default is flipped off MiniLM, **Then** DEFAULT_MODEL_NAME (embeddings.py:61), the model_name column DEFAULT (database.py:323), and the hardcoded literal (server.py:103) all read BAAI/bge-m3 — and server.py:103 (a health-diagnostic literal) reports the active model name rather than a fixed string so it cannot lie after the cutover. **And** the cos_doc_search threshold (docs.py:215, default 0.05) is raised to the BGE-M3 floor (0.60) and the cos_graph_similar cutoff likewise, so search does NOT return everything. **And** cos init vendors BGE-M3 (COS_ALLOW_MODEL_DOWNLOAD) or the ~4.3GB / 1024-dim install cost is explicitly documented, with COS_EMBEDDING_MODEL kept as a per-project opt-back-to-MiniLM escape hatch. **And** a doctor check flags a mixed-model population and the dogfood repo is migrated via make migrate-embeddings.

## Work Log
