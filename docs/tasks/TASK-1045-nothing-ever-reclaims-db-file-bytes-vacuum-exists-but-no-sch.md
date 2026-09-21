---
id: TASK-1045
title: "Nothing ever reclaims DB file bytes: VACUUM exists but no scheduled leg calls it"
swimlane: core
kind: chore
epic: null
labels: [parked]
status: complete
priority: P3
appetite: 1d
created: 2026-09-18
started: 2026-09-20
completed: 2026-09-20
agent_session: ses-claude-20260920-211122-bc06
depends_on: []
blocked_by: []
references: []
---
# TASK-1045: Nothing ever reclaims DB file bytes: VACUUM exists but no scheduled leg calls it

**Outcome (one sentence):** Dead pages come back on their own — a scheduled leg reclaims them at quiescence, or `cos doctor` says plainly that reclaiming is a manual step and names it.

## Work Log
- 2026-09-21 [claude]: Added a vacuum leg to the nightly run, placed right after memory_gc while the rows it deleted are still unreused free…
- 2026-09-21 [claude]: Status transitioned to complete via cos task-done.
