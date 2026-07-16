---
id: TASK-422
title: "Observability 'active' window uses board_os SSOT (P20) \u2014 Doctor/HUD agreement"
swimlane: infra
kind: chore
epic: null
labels: [ready]
status: archive
priority: P3
appetite: 1d
created: 2026-06-15
started: 2026-06-15
completed: 2026-06-15
agent_session: ses-claude-20260614-214422-d991
depends_on: []
blocked_by: []
references: []
---
# TASK-422: Observability 'active' window uses board_os SSOT (P20) — Doctor/HUD agreement

**Outcome (one sentence):** /api/observability/sessions and /api/board/list agree on whether a session is 'active': observability.py imports ACTIVE_WINDOW_SECS from board_os.presence instead of hardcoding 120.0.

## Work Log
