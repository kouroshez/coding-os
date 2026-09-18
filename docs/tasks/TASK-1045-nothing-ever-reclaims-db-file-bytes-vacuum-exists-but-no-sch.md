---
id: TASK-1045
title: "Nothing ever reclaims DB file bytes: VACUUM exists but no scheduled leg calls it"
swimlane: core
kind: chore
epic: null
labels: [parked]
status: icebox
priority: P3
appetite: 1d
created: 2026-09-18
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-1045: Nothing ever reclaims DB file bytes: VACUUM exists but no scheduled leg calls it

**Outcome (one sentence):** Dead pages come back on their own — a scheduled leg reclaims them at quiescence, or `cos doctor` says plainly that reclaiming is a manual step and names it.

## Work Log
