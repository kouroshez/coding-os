---
id: TASK-250
title: "Relocate dashboard widgets to Diagnostics>Overview, remove orphan route"
swimlane: core
kind: refactor
epic: hub-redesign
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-08
started: 2026-06-08
completed: 2026-06-08
agent_session: ses-claude-20260608-024900-f2b0
depends_on: []
blocked_by: []
references: []
---
# TASK-250: Relocate dashboard widgets to Diagnostics>Overview, remove orphan route

**Outcome (one sentence):** Relocate the Mission-Control widgets to Diagnostics>Overview and remove the orphan dashboard route.

## Read First
- src/core/web/ui/src/pages/DashboardPage.tsx — the widgets (cost-7d, board-summary, recent-traces) + their fetches.
- src/core/web/ui/src/pages/DiagnosticsPage.tsx — add an Overview sub-tab.
- src/core/web/ui/src/App.tsx — remove the orphan /workspace/dashboard route (chat is now the landing).

## Context / Approach
Move the 3 real telemetry widgets (fetches unchanged) into a new Diagnostics>Overview sub-tab, THEN delete the orphan /workspace/dashboard route + DashboardPage-as-landing. The chat-first landing (shipped) already replaced the dashboard; this just rehomes the wanted widgets so nothing is stranded.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** chat is the landing, **When** opening Diagnostics>Overview, **Then** cost/board-summary/recent-traces render there.
- **Given** /workspace/dashboard, **When** navigated, **Then** it no longer resolves as a landing.

## Work Log
- 2026-06-08 [claude]: Re-homed DashboardPage as Diagnostics>Overview (new tab + routes, index→overview, title→Overview); removed orphan /works
