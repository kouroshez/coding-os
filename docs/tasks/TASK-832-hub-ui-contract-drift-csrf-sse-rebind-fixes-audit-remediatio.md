---
id: TASK-832
title: "Hub UI: contract-drift + CSRF + SSE-rebind fixes (audit remediation)"
swimlane: core
kind: bug
epic: null
labels: [hub, frontend, audit, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-07-17
started: 2026-07-17
completed: 2026-07-17
agent_session: ses-claude-20260717-014556-89d0
depends_on: []
blocked_by: []
references: []
---
# TASK-832: Hub UI: contract-drift + CSRF + SSE-rebind fixes (audit remediation)

**Outcome (one sentence):** Hub UI components read the producer's real response shape, send CSRF on mutations, and re-scope live streams on project switch — closing the confirmed frontend defects from the hub audit.

## Read First
- src/core/web/ui/src/lib/api-client.ts
- src/core/web/ui/src/lib/hooks.ts
- src/core/rules/api-contract-discipline.md

## Repro Steps
HealthAlarmBar reads doctor.data.data.stats (double .data) — apiGet already unwrapped one, so every alarm is永 dead. Dashboard/CommandPalette read card.task_id but /api/board/list emits id. MemoryPage POSTs omit X-CSRF-Token (403). LogsPage SSE effect deps omit slug so it never re-binds on project switch.

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** /api/graph/doctor returns {data:{healthy,stats}} **When** HealthAlarmBar reads it **Then** it uses one .data and alarms fire on issue_count>0. **Given** /api/board/list emits card.id **When** Dashboard/CommandPalette render **Then** they read c.id not c.task_id. **Given** a MemoryPage vote/run **When** it POSTs **Then** it sends the CSRF header and does not show success on failure. **Given** a project switch **When** LogsPage live-tail is on **Then** the SSE re-subscribes to the new slug. **When** typecheck + vitest run **Then** they pass.

## Work Log
- 2026-07-17 [claude]: Frontend cluster committed (25cc4548, 8 files): HealthAlarmBar double-.data removed (alarms fire again);…
- 2026-07-17 [claude]: Status transitioned to complete via cos task-done.
