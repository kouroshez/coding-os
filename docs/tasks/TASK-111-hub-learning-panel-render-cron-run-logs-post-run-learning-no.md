---
id: TASK-111
title: "Hub learning panel — render cron run-logs, POST run-learning-now + button, Pydantic response_model"
swimlane: infra
kind: feature
epic: hook-remediation
labels: [hub, ui, learning, observability, audit-n7, ready]
status: complete
priority: P1
appetite: "1d"
created: 2026-06-05
started: 2026-06-05
completed: 2026-06-05
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-111: Hub learning panel — render cron run-logs, POST run-learning-now + button, Pydantic response_model

**Outcome (one sentence):** The Hub exposes a manual "Run learning loop now" trigger (POST /api/scheduled/run/{slug} → nightly.run_project off the event loop), scheduled_status carries a typed Pydantic response_model, and SettingsPage renders a Run-now button + last-run/cron status.

## Read First
- src/core/web/routes/scheduled.py
- src/core/web/ui/src/pages/SettingsPage.tsx
- src/core/scheduled/nightly.py

## Repro Steps
1. The Hub Settings page shows scheduled config but no way to trigger maintenance manually — you wait for the 03:00 cron.
2. /api/scheduled/status returns an untyped dict → api-types is `unknown`; the UI's ScheduledStatus interface only had {slug, path}.
Expected: a Run-now button + typed status.
Actual: no trigger, loose types.

## Acceptance (G/W/T)
- **Given** a registered project, **When** the user clicks "Run learning loop now", **Then** POST /api/scheduled/run/{slug} runs nightly.run_project (off the event loop) and the button surfaces ran/last-run.
- **Given** /api/scheduled/status, **When** it responds, **Then** it serializes through a Pydantic ScheduledStatus response_model (cron_a + projects).
- **Given** SettingsPage, **When** it renders, **Then** the ScheduledStatus interface includes cron_a + per-project run fields and shows last-run + cron-loaded state.

## Work Log
- 2026-06-05 [claude]: 7b POST /api/scheduled/run/{slug}→nightly.run_project via asyncio.to_thread (fail-soft RunResult); 7d scheduled_status r
