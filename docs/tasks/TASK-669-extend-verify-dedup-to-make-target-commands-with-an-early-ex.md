---
id: TASK-669
title: "Extend verify-dedup to make-target commands with an early-exit before the run-lock acquire"
swimlane: core
kind: feature
epic: test-discipline
labels: [tests, governor, dedup, ready]
status: icebox
priority: P2
appetite: 1d
created: 2026-06-30
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-669: Extend verify-dedup to make-target commands with an early-exit before the run-lock acquire

**Outcome (one sentence):** test-governor dedup covers make-target verify commands (not only bare pytest), and the dedup short-circuit runs BEFORE the run-lock acquire so a suite already green on the current tree exits early instead of contending for or starving on the host-global .test-run.lock.

## Read First
- src/core/hooks/test-governor.sh
- src/core/hooks/record-verify-auto.sh
- docs/engineering/test-governance.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a make verify-target already recorded green on the current tree, **When** it is re-invoked, **Then** test-governor dedups it with an early exit, the same as a bare pytest re-run.
- **Given** the dedup hit, **When** it short-circuits, **Then** it returns BEFORE acquiring .test-run.lock so a no-op never contends for the lock.
- **Given** a tree change, **When** the suite is invoked, **Then** the recorded pass is invalidated and the run proceeds normally.

## Work Log
