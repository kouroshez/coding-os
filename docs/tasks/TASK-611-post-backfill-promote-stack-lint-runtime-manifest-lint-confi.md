---
id: TASK-611
title: "(post-backfill) promote stack-lint runtime-manifest/lint-config/reference-integrity SOFT to HARD"
swimlane: cli
kind: chore
epic: stack-factory-v2
labels: []
status: icebox
priority: P2
appetite: 1d
created: 2026-06-27
started: null
completed: null
agent_session: null
depends_on: [TASK-605, TASK-606, TASK-607, TASK-608, TASK-599]
blocked_by: []
references: []
---

# TASK-611: (post-backfill) promote stack-lint runtime-manifest/lint-config/reference-integrity SOFT to HARD

**Outcome (one sentence):** After bootable + skill backfill closes the gaps, flip the T3 (TASK-598) SOFT checks — runtime-manifest, lint-config-where-commanded, reference-integrity — to HARD/blocking so a future stack can never regress below the v2 bar. Deliberately left SOFT until now to avoid turning CI red across 8 stacks at once (the staged promotion the adversarial critic insisted on).

## Work Log
