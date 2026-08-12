---
id: TASK-952
title: "Doctor: graph alarm reads an unwrapped envelope and the graph tab is labelled Backend"
swimlane: core
kind: bug
epic: null
labels: [ready]
status: complete
priority: P1
appetite: 1d
created: 2026-08-12
started: 2026-08-12
completed: 2026-08-12
agent_session: ses-claude-20260807-224955-abc1
depends_on: []
blocked_by: []
references: []
---
# TASK-952: Doctor: graph alarm reads an unwrapped envelope and the graph tab is labelled Backend

**Outcome (one sentence):** The header health alarm reports real graph issues because it reads the same envelope shape the producer emits, and the Doctor tab that probes graph_os is named for the graph rather than for "Backend".

## Read First
- src/core/web/ui/src/layout/HealthAlarmBar.tsx
- src/core/web/ui/src/pages/doctor/BackendTab.tsx
- src/core/web/ui/src/pages/doctor/doctor-shared.ts
- src/core/rules/api-contract-discipline.md

## Repro Steps
GET /api/p/coding-os/graph/doctor returns {data:{healthy,stats,issues}, meta:{}}. HealthAlarmBar reads doctor.data?.stats?.issue_count and doctor.data?.healthy ?? true, both of which resolve against the envelope rather than its data member, so issue_count is undefined -> 0 and healthy is undefined -> true. Verified in the live browser: j.stats === undefined while j.data.stats is present. BackendTab reads (doctor.data?.data ?? doctor.data) and renders correctly, so the two consumers of one route disagree.

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a graph doctor response whose data member reports issue_count above zero or healthy false
**When** the Hub header renders the health alarm
**Then** the alarm appears with the real issue count, a regression test pins the envelope shape both consumers read, and the Doctor tab probing graph_os is labelled for the knowledge graph.

## Work Log
- 2026-08-12 [claude]: Edit HealthAlarmBar.tsx
- 2026-08-12 [claude]: Edit doctor-shared.ts
- 2026-08-12 [claude]: Edit doctor-shared.ts
- 2026-08-12 [claude]: Status transitioned to complete via cos task-done.
