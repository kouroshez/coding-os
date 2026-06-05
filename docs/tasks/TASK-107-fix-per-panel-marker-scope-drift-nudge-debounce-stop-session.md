---
id: TASK-107
title: "Fix per-panel marker-scope drift — nudge debounce, Stop session-id, capture-work-log, intent.json, task-mode"
swimlane: core
kind: bug
epic: hook-remediation
labels: [hooks, multi-agent, state, audit-n3]
status: icebox
priority: P1
appetite: "1d"
created: 2026-06-05
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-107: Fix per-panel marker-scope drift — nudge debounce, Stop session-id, capture-work-log, intent.json, task-mode

**Outcome (one sentence):** Debounce markers written and cleared at the same scope (panel-dir); Stop hooks (session-end, warn-abandoned-task) read a non-empty session-id via stdin upgrade + agent-dir fallback; capture-work-log reads panel-dir .task-current; .intent.json + nudge markers panel-scoped.

## Read First
- src/core/hooks/session-context.sh
- src/core/hooks/nudge-thinking-os.sh
- src/core/hooks/session-end.sh
- src/core/hooks/cos-env.sh

## Repro Steps
1. (fill in: exact steps to reproduce)
2. ...
Expected: ...
Actual: ...

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** ...
- **When** ...
- **Then** ...

## Work Log
