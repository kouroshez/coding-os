---
id: TASK-146
title: "E12: nightly error-sweep — recurring durable errors become idempotent board bug tasks (fingerprint dedup)"
swimlane: infra
kind: feature
epic: observability-eye
labels: [observability, scheduled, error-pipeline, ready]
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
# TASK-146: E12: nightly error-sweep — recurring durable errors become idempotent board bug tasks (fingerprint dedup)

**Outcome (one sentence):** A dependency-injected error-sweep rolls log_events up into log_fingerprints and files one idempotent board bug task per fingerprint once it crosses a threshold (FATAL → P1 first hit; ERROR → after N occurrences / M sessions), excluding its own ops.error_sweep scope to avoid recursion; wired as a gated task in nightly.py.

## Read First
- docs/engineering/observability-eye.md
- src/core/scheduled/nightly.py
- src/core/scheduled/config.py
- src/core/logging_os/fingerprint.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** log_events holding a FATAL fingerprint and an ERROR fingerprint recurring ≥ the occurrence threshold (plus rows under ops.error_sweep)
- **When** run_error_sweep(conn, create_bug_task=<fake>) runs, then runs again
- **Then** log_fingerprints is rolled up (count / distinct_sessions / max_lvl), the FATAL + over-threshold ERROR fingerprints each yield exactly ONE bug task (the ops.error_sweep rows are excluded), the second run files nothing new (idempotent via status='filed'), --dry-run files nothing, and scheduled tests pass

## Work Log
- 2026-06-05 [claude]: E12: new scheduled/error_sweep.py (rollup_fingerprints + select_for_filing + run_error_sweep, DI creator, excludes ops.e
