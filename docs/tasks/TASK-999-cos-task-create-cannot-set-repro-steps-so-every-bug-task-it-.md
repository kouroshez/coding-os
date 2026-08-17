---
id: TASK-999
title: "cos task-create cannot set Repro Steps, so every bug task it creates is DoR-blocked"
swimlane: infra
kind: bug
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-08-17
started: 2026-08-16
completed: 2026-08-16
agent_session: ses-claude-20260814-120316-413b
depends_on: []
blocked_by: []
references: []
---
# TASK-999: cos task-create cannot set Repro Steps, so every bug task it creates is DoR-blocked

**Outcome (one sentence):** A bug task created from the CLI can be started immediately, because the CLI exposes the same Repro Steps field the MCP tool already accepts.

## Read First
- src/cli/_board_cli_lifecycle.py

## Repro Steps
1. `cos task-create --kind bug --title x --swimlane infra` — there is no `--repro` option, so the Repro Steps section keeps the template's placeholder line.
2. `cos task-start <ID>` → `ERROR [validation]: transition gate failed: [DOR_REPRO_STEPS_PLACEHOLDER]`.
3. The only way out is hand-editing the task body, which is what Rule 25 exists to discourage.

This very task was created that way. `mcp_tools.cos_task_create` already accepts `repro=`; only the CLI wrapper omits it.

Expected: a bug task created from the CLI is startable.
Actual: every one of them is DoR-blocked on a field the CLI cannot set.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** `cos task-create --kind bug --repro "..."`, **When** `cos task-start` runs on it, **Then** the transition succeeds instead of failing DOR_REPRO_STEPS_PLACEHOLDER.

## Work Log
- 2026-08-17 [claude]: Edit TASK-999-cos-task-create-cannot-set-repro-steps-so-every-bug-task-it-.md
- 2026-08-17 [claude]: Edit _board_cli_lifecycle.py
- 2026-08-17 [claude]: Edit _board_cli_lifecycle.py
- 2026-08-17 [claude]: Status transitioned to complete via cos task-done.
