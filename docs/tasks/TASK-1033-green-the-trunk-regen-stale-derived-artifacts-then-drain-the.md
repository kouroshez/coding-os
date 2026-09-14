---
id: TASK-1033
title: "Green the trunk: regen stale derived artifacts, then drain the icebox backlog"
swimlane: core
kind: chore
epic: null
labels: [ready]
status: testing
priority: P1
appetite: 1d
created: 2026-09-14
started: 2026-09-13
completed: null
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-1033: Green the trunk: regen stale derived artifacts, then drain the icebox backlog

**Outcome (one sentence):** CI on `main` is green and the icebox holds no pullable card: the two stale derived artifacts (scaffold manifest, doctor schema) are regenerated and every open icebox card is either fixed, re-scoped, or closed with evidence.

## Work Log
- 2026-09-14 [claude]: commit 540b3279b1 — chore: regen scaffold manifest and doctor schema to unblock red CI
