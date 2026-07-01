---
id: TASK-669
title: "Extend verify-dedup to make-target commands with an early-exit before the run-lock acquire"
swimlane: core
kind: feature
epic: test-discipline
labels: [tests, governor, dedup, ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-30
started: 2026-06-30
completed: 2026-06-30
agent_session: ses-claude-20260630-011740-9a32
depends_on: []
blocked_by: []
references: []
---
# TASK-669: Extend verify-dedup to make-target commands with an early-exit before the run-lock acquire

**Outcome (one sentence):** test-governor dedup covers make-target verify commands (not only bare pytest) so a suite already green on the current tree exits early — the lock-ordering half is ALREADY satisfied (dedup at test-governor.sh:92-105 returns before the lock at :107), so this task's only real work is extending SUITE detection to make-targets.

## Read First
- src/core/hooks/test-governor.sh
- src/core/hooks/record-verify-auto.sh
- docs/engineering/test-governance.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a make verify-target already recorded green on the current tree, **When** it is re-invoked, **Then** test-governor dedups it with an early exit, the same as a bare pytest re-run.
- **Given** the dedup hit, **When** it short-circuits, **Then** it returns before acquiring .test-run.lock — already true today, so preserve it, do not re-architect the lock.
- **Given** a tree change, **When** the suite is invoked, **Then** the recorded pass is invalidated and the run proceeds normally.

## Work Log
- 2026-07-01 [claude]: test-governor fast-paths + IS_PYTEST gate widened to make-target verify suites so a green make-verify dedups early…
- 2026-07-01 [claude]: committed 0d56c79f · 3 files
- 2026-07-01 [claude]: Status transitioned to complete via cos task-done.
