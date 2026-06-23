---
id: TASK-027
title: "HealthAlarmBar treat fetch errors as degraded state"
swimlane: core
kind: feature
epic: null
labels: [ui, observability, alarm]
status: archive
priority: P2
appetite: "30m"
created: 2026-05-23
started: 2026-05-23
completed: 2026-05-23
agent_session: ses-claude-20260523-010526-e647
depends_on: []
blocked_by: []
references:
  - src/core/web/ui/src/layout/HealthAlarmBar.tsx
---
# TASK-027: alarm bar flags backend-unreachable as degraded

**Outcome (one sentence):** Alarm chip in the top bar appears when the backend is unreachable (fetch errors on `/api/graph/doctor` or `/api/health`) — not just when the backend responds with `issue_count > 0` — closing the "silent when really broken" gap surfaced by the session /review.

## Read First
- [src/core/web/ui/src/layout/HealthAlarmBar.tsx](../../src/core/web/ui/src/layout/HealthAlarmBar.tsx) — current component, lines 27-32 lose the error case

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the backend is unreachable (FastAPI down, hub crashed, network partitioned)
- **When** the SPA polls `/api/graph/doctor` or `/api/health` and the fetch throws
- **Then** the AppShell renders an amber pill labelled "backend unreachable" linked to `/diagnostics/doctor`; `npm run build` clean.

## Work Log
- 2026-05-23 — added `backendUnreachable = Boolean(doctor.error || health.error)` derived from the two `useApiGet` calls; merged into `degraded` boolean + emits "backend unreachable" summary token first so it leads the chip when both pipes fail. `npm run build` clean (1.70 s, no TS errors).
- 2026-05-23 [claude]: Status transitioned to complete via cos task-done.
