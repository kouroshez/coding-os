---
id: TASK-067
title: "docs-update governance task loop policy in AGENTS and task-driver"
swimlane: docs
kind: docs
epic: null
labels: []
status: complete
priority: P2
appetite: "1d"
created: 2026-04-24
started: 2026-04-24
completed: 2026-04-24
agent_session: ses-cursor-20260424-061051-8b12
depends_on: []
blocked_by: []
references: []
---
# TASK-067: docs-update governance task loop policy in AGENTS and task-driver

**Outcome (one sentence):** Governance docs now enforce a deterministic task loop: reconcile existing tasks, create/fill when missing, handle blocked explicitly, test in `testing`, and close with concise logs.

## Read First
- `AGENTS.md` (Critical Rules + Core Loop + Tool Routing)
- `.claude/skills/task-driver/SKILL.md`
- `docs/tasks/TASK-066-harden-task-driver-workflow-and-agents-task-loop.md`

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a non-trivial implementation request
- **When** the governance and task-driver docs are followed
- **Then** the agent must reconcile existing tasks first, create one when absent, and fill Outcome/Read First/Acceptance before execution
- **And** status flow includes `blocked` handling and `in_progress -> testing -> complete` closure

## Work Log
- 2026-04-24 [cursor]: Created governance-scoped docs-update task required by policy hooks.
- 2026-04-24 [cursor]: Updated task-driver skill with mandatory intake loop + status choreography.
- 2026-04-24 [cursor]: Updated AGENTS with explicit task reconciliation rule and testing-stage close-out.
- 2026-04-24 [cursor]: Status transitioned to complete via cos task-done.
