---
id: TASK-087
title: "Ready hard-gate + testing-before-complete enforcement in Scrumban state machine"
swimlane: infra
kind: feature
epic: null
labels: [board, state-machine, scrumban]
status: archive
priority: P1
appetite: "1d"
created: 2026-06-04
started: 2026-06-04
completed: 2026-06-04
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-087: Ready hard-gate + testing-before-complete enforcement in Scrumban state machine

**Outcome (one sentence):** A non-ready icebox task cannot move to in_progress, and an in_progress task cannot jump to complete without passing through testing — both config-driven, with a cos_task_ready op as the gate key.

## Read First
- src/core/board_os/workflow.py
- src/core/board_os/config.py
- src/core/board_os/mcp_tools.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** an icebox task without the `ready` label and a config with `require_ready_label=true`
- **When** an agent calls `cos_task_move(to="in_progress")`
- **Then** the transition is BLOCKED with an actionable message, and succeeds only after `cos_task_ready` adds the label (emergency path stays exempt).
- **Given** an in_progress task and config `block_in_progress_to_complete=true`
- **When** an agent moves it directly to `complete`
- **Then** the transition is BLOCKED, forcing in_progress→testing→complete (bypass via force/bypass_gates).

## Work Log
- 2026-06-04 [claude]: Added config-driven ready-gate (icebox→in_progress needs 'ready' label, emergency exempt) + testing-gate (block in_progr
