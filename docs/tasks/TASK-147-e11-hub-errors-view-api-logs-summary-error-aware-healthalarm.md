---
id: TASK-147
title: "E11: Hub Errors view + /api/logs/summary + error-aware HealthAlarmBar (DB-backed, filterable)"
swimlane: infra
kind: feature
epic: observability-eye
labels: [observability, web, ui, deferred, ready]
status: complete
priority: P2
appetite: "1d"
created: 2026-06-05
started: 2026-06-05
completed: 2026-06-05
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-147: E11: Hub Errors view + /api/logs/summary + error-aware HealthAlarmBar (DB-backed, filterable)

**Outcome (one sentence):** /api/logs/summary returns counts-by-level + error/fatal counts + top error scopes from the live log feed, and HealthAlarmBar consumes it to surface "N errors / FATAL" (red on FATAL) so the Hub answers "what is broken now" at a glance.

## Read First
- docs/engineering/observability-eye.md
- src/core/web/routes/logs.py
- src/core/web/ui/src/layout/HealthAlarmBar.tsx
- src/core/web/ui/src/lib/hooks.ts

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the log feed holds recent WARN/ERROR/FATAL events
- **When** GET /api/logs/summary?since=1h is called and the Hub top bar renders
- **Then** the route returns {by_level, error_count, warn_count, fatal_count, top_error_scopes} (meta.layer=logs); HealthAlarmBar shows the error count (amber) and turns red with a FATAL count when any FATAL is present; and `make ui-build` succeeds

## Work Log
- 2026-06-05 [claude]: E11: added GET /api/logs/summary (counts-by-level + error/warn/fatal counts + top_error_scopes, reuses _read_tail_jsonl/
