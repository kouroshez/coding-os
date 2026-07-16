---
id: TASK-177
title: "Add formula_dispatches error column and capture dispatch failure reason at write sites"
swimlane: core
kind: bug
epic: agent-economy
labels: [ready]
status: archive
priority: P2
appetite: "1d"
created: 2026-06-05
started: 2026-06-05
completed: 2026-06-05
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-177: Add formula_dispatches error column and capture dispatch failure reason at write sites

**Outcome (one sentence):** formula_dispatches gains an error column via append-only migration v34, and both write sites (cos_supervise_record_output and the SDK dispatch persist) populate it on non-ok status so failed dispatches are diagnosable instead of logged-only.

## Read First

- docs/engineering/agent-economy-and-identity-roadmap.md (B5)
- src/core/thinking_os/database.py (MIGRATIONS list, _migrate_v23 pattern)
- src/core/thinking_os/tools/cognition.py (record_output insert ~L297, SDK persist ~L1087)

## Repro Steps

1. formula_dispatches has columns id/session_id/.../status but NO error column.
2. In cos_supervise_record_output, a parse failure flips status to fail (lines 271-285) and logs the exception at warning level, but the INSERT stores only status — the reason is lost.
3. Historically ~42% of exhaustive_evidence dispatch rows are status=fail with zero captured reason, making the one exercised dispatch path undiagnosable.

## Acceptance

- **Given** the v34 migration and the two write sites,
- **When** a dispatch is recorded with a non-ok status (e.g. a parse failure),
- **Then** the formula_dispatches row carries a non-null error string describing the failure, the column exists after migrations (asserted in test_db), and ASCII/ok dispatches store error=NULL.

## Work Log
- 2026-06-05 [claude]: Status transitioned to complete via cos task-done.
