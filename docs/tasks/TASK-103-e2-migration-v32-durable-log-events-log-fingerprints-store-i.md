---
id: TASK-103
title: "E2: migration v32 — durable log_events + log_fingerprints store in coding-os.db (append-only)"
swimlane: infra
kind: feature
epic: observability-eye
labels: [observability, logging_os, migration, database, ready]
status: archive
priority: P1
appetite: "1d"
created: 2026-06-05
started: 2026-06-05
completed: 2026-06-05
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-103: E2: migration v32 — durable log_events + log_fingerprints store in coding-os.db (append-only)

**Outcome (one sentence):** A new append-only migration v32 adds log_events (durable WARN+ error rows, indexed for query) + log_fingerprints (permanent rollup + idempotency anchor) to coding-os.db, so errors survive jsonl-tail truncation and process restart. user_version advances 31→32; no past migration edited (Rule 9).

## Read First
- docs/engineering/observability-eye.md
- src/core/thinking_os/database.py
- src/core/thinking_os/tests/test_db.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** coding-os.db migrated to v31 with no durable error store
- **When** run_migrations applies the appended v32 entry
- **Then** schema_version == 32 (== len(MIGRATIONS)); log_events + log_fingerprints exist with their indexes; the migration is idempotent (second run = no-op); and `uv run --extra rag pytest src/core/thinking_os/tests/test_db.py -q` is green, with test_all_tables_exist extended to include both new tables

## Work Log
- 2026-06-05 [claude]: Added migration v32 (_migrate_v32_log_events) + registry entry in database.py — log_events (durable WARN+ rows, indexed 
