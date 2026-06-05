---
id: TASK-147
title: "E11: Hub Errors view + /api/logs/summary + error-aware HealthAlarmBar (DB-backed, filterable)"
swimlane: infra
kind: feature
epic: observability-eye
labels: [observability, web, ui, deferred, ready]
status: icebox
priority: P2
appetite: "1d"
created: 2026-06-05
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-147: E11: Hub Errors view + /api/logs/summary + error-aware HealthAlarmBar (DB-backed, filterable)

**Outcome (one sentence):** Hub answers "what is broken now" at a glance — /api/logs/summary returns counts-by-level + top scopes from log_events (reuse log_query); LogsPage gains an error-only preset + count rollup + session filter; HealthAlarmBar turns red on an error storm; DoctorPage errorsHistory reads real data. Deferred from the eye epic — heavier React + ui-build slice; spec in observability-eye.md §3 + roadmap E11.

## Read First
- docs/engineering/observability-eye.md
- src/core/web/routes/logs.py
- src/core/web/ui/src/
- src/core/thinking_os/tools/logs.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** ...
- **When** ...
- **Then** ...

## Work Log
