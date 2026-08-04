---
id: TASK-795
title: "Fix embedding-outbox drain interpreter + self-healing reconciliation + BGE-M3 similarity floor"
swimlane: "thinking_os"
kind: bug
epic: null
labels: [ready]
status: archive
priority: P2
appetite: 1d
created: 2026-07-05
started: 2026-07-04
completed: 2026-07-05
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-795: Fix embedding-outbox drain interpreter + self-healing reconciliation + BGE-M3 similarity floor

**Outcome (one sentence):** The embedding-outbox drains under a rag-capable interpreter and self-heals already-embedded rows model-free, clearing the 2837-row 26-day backlog; semantic memory/task search uses the BGE-M3 calibrated floor (~0.55) instead of 0.05 so augmentation stops admitting near-random neighbours.

## Read First
- src/core/thinking_os/embeddings.py
- src/core/hooks/drain-embedding-outbox.sh
- src/core/hooks/cos-env.sh
- src/core/hooks/check-mcp-extras.sh
- src/core/thinking_os/tools/memory.py
- src/core/thinking_os/tools/tasks.py

## Repro Steps
python3 -c 'import sentence_transformers' → ModuleNotFoundError; drain-embedding-outbox.sh:17 runs bare python3 → is_available() False → drain_outbox returns unavailable before the loop; live embedding_outbox=2837 all attempts=0, 669 already-embedded, observation embeddings frozen since 2026-06-12; memory.py threshold=0.05 vs BGE-M3 calibrated noise floor ~0.55.

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** drain-embedding-outbox.sh runs bare python3 (no sentence_transformers) so is_available() is False and 2837 outbox rows sit at attempts=0 with 669 already embedded **When** the drain runs under a rag-capable interpreter resolved via cos_resolve_python and a model-free reconciliation DELETE runs before the availability guard, and search_similar uses memory_similarity_floor() **Then** already-embedded outbox rows reconcile to 0, the backlog embeds after a reindex, and memory_search/task_search semantic augmentation is called with threshold≈0.55 (BGE-M3) not 0.05.

## Work Log
- 2026-07-05 [claude]: Edit embeddings.py
- 2026-07-05 [claude]: Edit embeddings.py
- 2026-07-05 [claude]: Edit memory.py
- 2026-07-05 [claude]: Edit tasks.py
- 2026-07-05 [claude]: Edit tasks.py
- 2026-07-05 [claude]: Edit tasks.py
- 2026-07-05 [claude]: Edit cos-env.sh
- 2026-07-05 [claude]: Edit drain-embedding-outbox.sh
- 2026-07-05 [claude]: Edit check-mcp-extras.sh
- 2026-07-05 [claude]: Edit registry.yaml
- 2026-07-05 [claude]: Edit test_embeddings.py
- 2026-07-05 [claude]: Edit test_embeddings.py
- 2026-07-05 [claude]: embeddings.py: model-free reconciliation DELETE before is_available() guard + drain limit 64→128 +…
- 2026-07-05 [claude]: committed 641a28a8 · 9 files
