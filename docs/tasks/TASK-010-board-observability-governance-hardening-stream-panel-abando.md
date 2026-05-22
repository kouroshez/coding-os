---
id: TASK-010
title: "Board observability + governance hardening — stream panel, abandoned-task hook, move attribution, assign guard"
swimlane: infra
kind: chore
epic: null
labels: [board, observability, governance]
status: complete
priority: P2
appetite: "1d"
created: 2026-05-22
started: 2026-05-21
completed: 2026-05-21
agent_session: ses-claude-20260521-211251-2da3
depends_on: []
blocked_by: []
references: []
---
# TASK-010: Board observability + governance hardening — stream panel, abandoned-task hook, move attribution, assign guard

**Outcome (one sentence):** Agent Stream panel loads board history on every open; abandoned in_progress tasks get flagged at session end; every task move records its agent_session; agents are blocked from moving tasks they were not assigned/instructed to touch.

## Work Log
- 2026-05-22 [claude]: Group A: useBoardStream cache now sessionStorage-backed (survives reload), history bootstrap limit 20→100, MAX_EVENTS 12
