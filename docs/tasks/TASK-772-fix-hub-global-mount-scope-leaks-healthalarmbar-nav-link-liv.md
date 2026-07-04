---
id: TASK-772
title: "Fix Hub global-mount scope leaks: HealthAlarmBar nav link, LiveStatus SSE deps, Memory/Overview guards"
swimlane: core
kind: bug
epic: null
labels: [ready]
status: in_progress
priority: P2
appetite: 1d
created: 2026-07-04
started: 2026-07-04
completed: null
agent_session: ses-claude-20260703-210450-473d
depends_on: []
blocked_by: []
references: []
---
# TASK-772: Fix Hub global-mount scope leaks: HealthAlarmBar nav link, LiveStatus SSE deps, Memory/Overview guards

**Outcome (one sentence):** Three scope-awareness gaps closed: HealthAlarmBar's diagnostics link is scope-aware, LiveStatus's hook-stream SSE re-subscribes when the active project changes, and Memory/Overview pages guard reads when no project is scoped instead of silently showing the launch project.

## Read First
- src/core/web/ui/src/layout/HealthAlarmBar.tsx
- src/core/web/ui/src/layout/LiveStatus.tsx
- src/core/web/ui/src/pages/MemoryPage.tsx
- src/core/web/ui/src/pages/DashboardPage.tsx

## Repro Steps
Scope to /p/<slug>, click the HealthAlarmBar doctor link → lands on global /diagnostics/doctor (launch project). Switch projects → LiveStatus hook-tick stays pinned to the first project (SSE useEffect has empty deps). Open global /diagnostics/memory with no project → shows launch project's patterns with no indication.

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** the Hub scoped to /p/<slug> **When** the HealthAlarmBar diagnostics link is clicked **Then** it navigates to the scoped diagnostics route, not the global one. **Given** the user switches from project A to project B **When** LiveStatus is mounted in the persistent shell **Then** its SSE re-subscribes to project B's hook stream. **Given** no project is scoped (global mount) **When** Memory/Overview render **Then** they show a select-a-project state rather than the launch project's data.

## Work Log
- 2026-07-04 [claude]: Fixed 4a (HealthAlarmBar diagnostics Link now uses scopedLink) + 4b (LiveStatus hook-stream SSE effect deps []→[slug]…
