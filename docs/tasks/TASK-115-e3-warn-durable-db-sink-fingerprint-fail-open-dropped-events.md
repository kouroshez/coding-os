---
id: TASK-115
title: "E3: WARN+ durable DB sink + fingerprint + fail-open dropped_events counter in logging_os"
swimlane: infra
kind: feature
epic: observability-eye
labels: [observability, logging_os, sink, durability, ready]
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
# TASK-115: E3: WARN+ durable DB sink + fingerprint + fail-open dropped_events counter in logging_os

**Outcome (one sentence):** sinks.dispatch() persists WARN+ events to log_events (computing a stable fingerprint at insert) while debug/info stay jsonl-tail-only (hot path untouched); the DB write is fail-open and increments an observable dropped_events counter on any failure, never re-entering logging_os (invariant I1).

## Read First
- docs/engineering/observability-eye.md
- src/core/logging_os/sinks.py
- src/core/logging_os/config.py
- src/core/logging_os/tests/test_sinks.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a coding-os.db migrated to v32 and COS_LOG_DB_MIN_LEVEL=WARN
- **When** logging_os emits an ERROR then a DEBUG event
- **Then** the ERROR appears as a log_events row (with a computed fingerprint) AND in the jsonl tail; the DEBUG appears only in the jsonl tail (no DB row); and an injected INSERT failure increments sinks.dropped_events() without losing the jsonl/stderr line

## Work Log
- 2026-06-05 [claude]: Added WARN+ sqlite sink to logging_os: config.db_path()/db_min_level(); new fingerprint.py (normalize_msg+fingerprint, s
