---
id: TASK-464
title: "Drop dead experiment_log table (B5 hygiene)"
swimlane: "thinking_os"
kind: refactor
epic: audit-remediation-2026-06
labels: [audit-remediation, cleanup, ready]
status: archive
priority: P3
appetite: 1d
created: 2026-06-20
started: 2026-06-19
completed: 2026-06-19
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-464: Drop dead experiment_log table (B5 hygiene)

**Outcome (one sentence):** experiment_log (created in v1, zero production writers across 260 tasks — fully-built-but-unwired speculation) is removed via migration v43 + all readers (dashboard, stats lists, doctor-config, seed/tests, schema doc); the other 4 empty tables (ambiguity_violations/memory_audit/pattern_validations/retrieval_quality) are KEPT — each has a real code writer and is latent-not-dead.

## Read First
- src/core/thinking_os/database.py
- src/core/thinking_os/dashboard.py
- src/core/doctor-config.yaml

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a fresh or migrated DB, **When** init_db runs, **Then** experiment_log no longer exists (migration v43 drops it) and get_db_stats omits it.
**Given** the thinking_os matrix suite, **When** run, **Then** green with no experiment_log references remaining in code or tests.
**Given** the 4 wired empty tables, **When** audited, **Then** each retains its writer and is documented as latent (not dropped).

## Work Log
- 2026-06-20 [claude]: commit 8bd3575376 — refactor(thinking_os): drop dead experiment_log table (B5)
- 2026-06-20 [claude]: Status transitioned to complete via cos task-done.
- 2026-06-20 [claude]: committed c4e2432a · 1 file
