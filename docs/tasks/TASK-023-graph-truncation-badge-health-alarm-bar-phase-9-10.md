---
id: TASK-023
title: "graph truncation badge + health alarm bar (Phase 9 + 10)"
swimlane: core
kind: feature
epic: null
labels: [ui, observability, graph]
status: archive
priority: P1
appetite: "1h"
created: 2026-05-23
started: 2026-05-23
completed: 2026-05-23
agent_session: ses-claude-20260523-010526-e647
depends_on: []
blocked_by: []
references:
  - src/core/web/ui/src/features/graph/GraphCanvas.tsx
  - src/core/web/ui/src/layout/HealthAlarmBar.tsx
  - src/core/web/ui/src/layout/AppShell.tsx
---
# TASK-023: Phase 9 truncation badge + Phase 10 alarm bar

**Outcome (one sentence):** Graph canvas surfaces "X / Y nodes" so users *see* when the budget truncates the view, and the AppShell top bar shows an amber chip the moment graph_os reports issues or `/health` degrades — giving the user the alarm signal they explicitly asked for: when something breaks, the system must raise an alarm.

## Read First
- [src/core/web/ui/src/features/graph/GraphCanvas.tsx](../../src/core/web/ui/src/features/graph/GraphCanvas.tsx) — gains the bottom-right truncation badge
- [src/core/web/ui/src/layout/HealthAlarmBar.tsx](../../src/core/web/ui/src/layout/HealthAlarmBar.tsx) — new component; polls `/api/graph/doctor` + `/api/health` every 30 s
- [src/core/web/ui/src/layout/AppShell.tsx](../../src/core/web/ui/src/layout/AppShell.tsx) — mounts the bar next to LiveStatus

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the graph canvas renders any subgraph
- **When** the rendered subgraph has been truncated by the requested-max budget
- **Then** a bottom-right badge shows `<shown>/<fetched> nodes` and an amber "truncated · raise depth budget" hint appears next to it.

- **Given** the system is healthy (graph_doctor issue_count=0, /health=ok)
- **When** the user opens any page
- **Then** the AppShell renders no alarm chip (silent).

- **Given** graph_doctor reports any issue OR /health is degraded
- **When** the user opens any page
- **Then** an amber `⚠ <N> graph issues` chip appears in the top bar; clicking it navigates to `/diagnostics/doctor`.

## Work Log
- 2026-05-23 — added bottom-right truncation badge to `GraphCanvas.tsx` (shows `<shown>/<fetched> nodes` + amber "raise depth budget" hint when fetched ≥ requestedMax); new `HealthAlarmBar.tsx` component polls `/api/graph/doctor` + `/api/health` every 30 s and renders an amber chip only when degraded (silent when healthy), linked to `/diagnostics/doctor`; wired into AppShell next to LiveStatus. `npm run build` clean (1.78s, no TS errors).
- 2026-05-23 [claude]: Status transitioned to complete via cos task-done.
