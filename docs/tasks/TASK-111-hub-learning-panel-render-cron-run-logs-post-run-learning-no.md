---
id: TASK-111
title: "Hub learning panel — render cron run-logs, POST run-learning-now + button, Pydantic response_model"
swimlane: infra
kind: feature
epic: hook-remediation
labels: [hub, ui, learning, observability, audit-n7]
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

# TASK-111: Hub learning panel — render cron run-logs, POST run-learning-now + button, Pydantic response_model

**Outcome (one sentence):** Hub surfaces learning-loop run-logs (cron_a + per-project last_run_at/tasks/failures); a 'Run learning loop now' button hits a new POST /api/scheduled/run; scheduled_status gains a Pydantic response_model so the consumer can't drop fields.

## Read First
- src/core/web/routes/scheduled.py
- src/core/web/ui/src/pages/SettingsPage.tsx
- src/core/web/ui/src/pages/MemoryPage.tsx

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** ...
- **When** ...
- **Then** ...

## Work Log
