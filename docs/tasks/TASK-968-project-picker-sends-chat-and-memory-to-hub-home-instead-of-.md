---
id: TASK-968
title: "Project picker sends chat and memory to Hub home instead of the chosen project"
swimlane: core
kind: bug
epic: null
labels: [hub-ui, routing, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-08-14
started: 2026-08-14
completed: 2026-08-14
agent_session: ses-claude-20260812-170221-1654
depends_on: []
blocked_by: []
references: []
---
# TASK-968: Project picker sends chat and memory to Hub home instead of the chosen project

**Outcome (one sentence):** Picking a project from the unscoped picker lands on that project's same tab, for every feature, with no bounce through Hub home.

## Read First
- src/core/web/ui/src/pages/NeedProjectPage.tsx
- src/core/web/ui/src/App.tsx
- src/core/web/ui/src/lib/use-scoped-link.ts

## Repro Steps
Open http://127.0.0.1:9188/workspace/chat with no project selected. The NeedProjectPage picker appears. Click OPEN on any project. Expected: /p/<slug>/workspace/chat. Actual: navigates to /p/<slug>/chat, which matches no route, falls through to the `*` catch-all, and redirects to `/` (Hub home). Same for memory. board/search happen to work only because App.tsx lines 124-125 carry flat redirects that chat and memory lack.

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** the unscoped picker for any workspace tab, **When** a project is chosen, **Then** the URL becomes /p/<slug>/workspace/<tab> and the tab renders. **Given** a bookmarked flat URL /p/<slug>/chat, **When** opened, **Then** it redirects into the workspace tab rather than Hub home.

## Work Log
- 2026-08-14 [claude]: Edit NeedProjectPage.routing.test.tsx
- 2026-08-14 [claude]: Edit NeedProjectPage.routing.test.tsx
- 2026-08-14 [claude]: Edit use-scoped-link.ts
- 2026-08-14 [claude]: Edit NeedProjectPage.tsx
- 2026-08-14 [claude]: Edit NeedProjectPage.tsx
- 2026-08-14 [claude]: Edit App.tsx
- 2026-08-14 [claude]: Edit App.tsx
- 2026-08-14 [claude]: Edit App.tsx
- 2026-08-14 [claude]: Edit NeedProjectPage.routing.test.tsx
- 2026-08-14 [claude]: commit f717e2d928 — fix(hub-ui): picking a project no longer bounces chat and memory to Hub home
- 2026-08-14 [claude]: Status transitioned to complete via cos task-done.
