---
id: TASK-281
title: "Wave 4: embedding outbox \u2014 durable backfill of hot-path-skipped embeddings off the interactive path"
swimlane: "thinking_os"
kind: feature
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-09
started: 2026-06-09
completed: 2026-06-09
agent_session: ses-claude-20260608-203030-6c0f
depends_on: []
blocked_by: []
references: []
---
# TASK-281: Wave 4: embedding outbox — durable backfill of hot-path-skipped embeddings off the interactive path

**Outcome (one sentence):** capture's hot-path embed-skip enqueues to a durable embedding_outbox instead of dropping; a Stop-hook drains it off the interactive path so every observation eventually gets an embedding without blocking Edits; idempotent, bounded, retry-on-failure; green tests.

## Read First
- src/core/thinking_os/capture.py
- src/core/thinking_os/embeddings.py
- src/core/thinking_os/database.py
- src/core/hooks/registry.yaml

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** an observation captured on the hot path (COS_CAPTURE_SKIP_EMBED) with no embedding
- **When** the capture runs and later the outbox is drained
- **Then** an embedding_outbox row is enqueued at capture time (no model load on the hot path), drain_outbox embeds it and removes the row, a failed embed increments attempts + records last_error (no infinite retry), drain is bounded + idempotent, and a Stop hook drains off the interactive path; new + existing tests green.

## Work Log
- 2026-06-09 [claude]: DONE. migration v40 embedding_outbox (UNIQUE source_table+source_id, idempotent). embeddings.enqueue_outbox (cheap INSER
