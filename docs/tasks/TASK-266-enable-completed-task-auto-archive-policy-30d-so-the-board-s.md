---
id: TASK-266
title: "Enable completed-task auto-archive policy (30d) so the board self-bounds"
swimlane: core
kind: chore
epic: hub-redesign
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-08
started: 2026-06-08
completed: 2026-06-08
agent_session: ses-claude-618-2ab7
depends_on: []
blocked_by: []
references: []
---
# TASK-266: Enable completed-task auto-archive policy (30d) so the board self-bounds

**Outcome (one sentence):** Completed tasks idle >30 days auto-archive (reversible, keep/parked-exempt) on cos daily + nightly, so the COMPLETE column self-bounds to recent work instead of growing without limit; icebox stays manual.

## Work Log
- 2026-06-08 [claude]: Set complete_auto_archive_days default 0→30 in config.py and the _base scaffold scrumban-config (icebox stays 0 — never 
