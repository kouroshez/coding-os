---
id: TASK-086
title: "Remove non-functional stub metrics (LEAD TIME, STALE) from Hub board metrics bar"
swimlane: infra
kind: chore
epic: null
labels: [ui, board, cleanup]
status: archive
priority: P3
appetite: "1d"
created: 2026-06-04
started: 2026-06-04
completed: 2026-06-04
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-086: Remove non-functional stub metrics (LEAD TIME, STALE) from Hub board metrics bar

**Outcome (one sentence):** Hub board top bar no longer shows always-empty LEAD TIME / STALE tiles; only real computed metrics remain.

## Work Log
- 2026-06-04 [claude]: Removed LEAD TIME + STALE stub StatCells (always-null) from board top bar; dropped unused BoardStats fields leadTime/lea
