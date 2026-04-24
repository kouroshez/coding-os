---
id: TASK-066
title: "Harden task-driver workflow and AGENTS task loop"
swimlane: core
kind: refactor
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
# TASK-066: Harden task-driver workflow and AGENTS task loop

**Outcome (one sentence):** Task governance is explicit and enforceable: every user request is reconciled against existing tasks, new work always gets a filled task, and status progression follows `in_progress -> testing -> complete` with concise work-log discipline.

## Read First
- `.claude/skills/task-driver/SKILL.md`
- `AGENTS.md` (Rules + Core Loop + Tool Routing)
- `core/board_os/mcp_tools.py` (`cos_task_create` template semantics)

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a new user request that implies implementation work
- **When** task-driver guidance is applied
- **Then** the agent first reconciles existing tasks, creates one if missing, fills Outcome/Read First/Acceptance before starting, and transitions through `in_progress -> testing -> complete`
- **And** blocked conditions are surfaced with an explicit move to `blocked`
- **And** completion requires tests + one concise work-log note

## Work Log
- 2026-04-24 [cursor]: Created and started TASK-066.
- 2026-04-24 [cursor]: Tightened task-driver skill with mandatory request intake loop, task-content completion gate, explicit blocked/testing flow, and concise work-log policy.
- 2026-04-24 [cursor]: Updated AGENTS task governance text to match skill behavior and remove ambiguity about when to create/reuse tasks.
- 2026-04-24 [cursor]: Status transitioned to complete via cos task-done.
