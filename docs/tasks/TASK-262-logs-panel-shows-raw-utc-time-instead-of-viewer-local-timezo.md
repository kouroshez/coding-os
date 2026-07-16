---
id: TASK-262
title: "Logs panel shows raw UTC time instead of viewer-local timezone"
swimlane: core
kind: bug
epic: hub-redesign
labels: [hub, logs, timezone, ready]
status: archive
priority: P2
appetite: 1d
created: 2026-06-08
started: 2026-06-08
completed: 2026-06-08
agent_session: ses-claude-20260608-021813-db02
depends_on: []
blocked_by: []
references: []
---
# TASK-262: Logs panel shows raw UTC time instead of viewer-local timezone

**Outcome (one sentence):** LogsPage.shortTime() string-slices the UTC ISO timestamp (`iso.slice(11,19)`) so the Logs panel shows raw UTC (16:54:16) instead of viewer-local time (12:54:16 EDT); fix UI-side to parse with `new Date()` and render via `toLocaleTimeString`.

## Read First
- src/core/web/ui/src/pages/LogsPage.tsx (shortTime, line 35)
- src/core/web/ui/src/pages/MemoryPage.tsx (correct pattern: `new Date().toLocaleString()`)
- src/core/hooks/_helpers/tool_failure_capture.py (backend stamps `datetime.now(timezone.utc)` → `Z`)

## Repro Steps
1. Open the Hub Logs panel while the machine is NOT on UTC (e.g. EDT, UTC-4).
2. Compare a log row's `time` column to the wall clock.
Expected: time shown in the viewer's local timezone.
Actual: time is 4h ahead — it is the raw UTC time-of-day sliced from the `...T16:54:16Z` ISO string.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a log event stamped `2026-06-08T16:54:16Z` (UTC) viewed in a non-UTC timezone,
- **When** the Logs panel renders the time column via `shortTime`,
- **Then** it shows the viewer's LOCAL time (e.g. `12:54:16` in EDT) produced by `new Date(iso).toLocaleTimeString`, not the raw UTC slice; malformed/empty input falls back gracefully; a unit test pins the contract.

## Work Log
- 2026-06-08 [claude]: Fixed (fecd630a): LogsPage.shortTime now parses the UTC ISO with new Date() and renders via toLocaleTimeString(undefined
