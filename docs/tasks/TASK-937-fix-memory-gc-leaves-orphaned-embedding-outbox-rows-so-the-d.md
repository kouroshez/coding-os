---
id: TASK-937
title: "fix: memory_gc leaves orphaned embedding_outbox rows so the drain starves"
swimlane: core
kind: bug
epic: null
labels: [ready]
status: complete
priority: P1
appetite: 1d
created: 2026-08-11
started: 2026-08-11
completed: 2026-08-11
agent_session: ses-claude-20260807-224955-abc1
depends_on: []
blocked_by: []
references: []
---
# TASK-937: fix: memory_gc leaves orphaned embedding_outbox rows so the drain starves

**Outcome (one sentence):** The embedding outbox holds only rows whose source still exists, and a drain that drops rows reports the count instead of exiting silently.

## Read First
- src/core/thinking_os/memory_gc.py — `gc_memory` sweeps orphan embeddings but never `embedding_outbox`
- src/core/thinking_os/embeddings.py — `drain_outbox`
- src/core/hooks/_helpers/drain_embedding_outbox.py — the Stop-hook caller

## Repro Steps
1. `SELECT COUNT(*) FROM embedding_outbox` → 3,593, all `source_table='observations'`.
2. Count rows whose observation was reaped: 2,698 (75%).
3. Run the Stop-hook helper with stderr visible → **no output at all**, exit 0.
4. Call `embeddings.drain_outbox(conn, limit=8)` → `{'status': 'ok', 'drained': 0, 'failed': 0}` while `remaining` falls by 8.

Expected: the drain makes visible progress, or says why it cannot.
Actual: `drain_outbox` deletes a source-less row at embeddings.py:760-762 without counting it, so a batch of pure orphans returns `drained=0, failed=0`; the helper only prints when `drained` is truthy, so two months of sessions logged `ok` while 97.4% of observations stayed unembedded. The observation TTL reaps rows the outbox still references, and `gc_memory` covers `embeddings` but not `embedding_outbox`.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** an outbox row whose source row no longer exists, **When** `gc_memory` runs, **Then** the row is deleted in that pass and the count appears in its stats.
- **Given** a drain batch consisting only of source-less rows, **When** `drain_outbox` returns, **Then** the report carries a non-zero `dropped` count and the hook helper prints it to stderr.
- **Given** the live database, **When** the sweep runs once, **Then** the orphan count falls to 0 and the remaining outbox equals the rows whose observation still exists.

## Work Log
- 2026-08-11 [claude]: Edit memory_gc.py
- 2026-08-11 [claude]: Edit memory_gc.py
- 2026-08-11 [claude]: Edit embeddings.py
- 2026-08-11 [claude]: Edit embeddings.py
- 2026-08-11 [claude]: Edit drain_embedding_outbox.py
- 2026-08-11 [claude]: Edit test_concept_graph.py
- 2026-08-11 [claude]: Edit test_concept_graph.py
- 2026-08-11 [claude]: Edit test_concept_graph.py
- 2026-08-11 [claude]: Edit memory_gc.py
- 2026-08-11 [claude]: Edit memory_gc.py
- 2026-08-11 [claude]: Edit test_concept_graph.py
- 2026-08-11 [claude]: Edit test_concept_graph.py
- 2026-08-11 [claude]: Edit memory_gc.py
- 2026-08-11 [claude]: Edit memory_gc.py
- 2026-08-11 [claude]: commit 5c809ae414 — fix(memory): sweep orphaned outbox rows so the embedding drain stops starving
- 2026-08-11 [claude]: Status transitioned to complete via cos task-done.
