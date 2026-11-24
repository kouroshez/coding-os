---
id: TASK-1101
title: "feat(hooks): the agent echoes each live board line in its reply, like the banner"
swimlane: core
kind: feature
epic: null
labels: [hooks, governance, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-11-24
started: 2026-11-23
completed: 2026-11-23
agent_session: ses-claude-20261123-135444-89e7
depends_on: []
blocked_by: []
references: []
---
# TASK-1101: feat(hooks): the agent echoes each live board line in its reply, like the banner

**Outcome (one sentence):** Task creates and moves are visible in the desktop app's default transcript view, because the agent writes each board line into its own text the moment the hook hands it over.

## Read First
- src/core/rules/transparency-banner.md
- src/core/hooks/show-board-transition.sh
- tests/test_warn_abandoned_task.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** an agent moves a task through cos_task_move or cos task-move, **When** show-board-transition.sh runs, **Then** its output keeps the systemMessage and adds a PostToolUse additionalContext carrying the same lines and the echo instruction.
- **Given** the rule transparency-banner.md, **When** an agent receives BOARD_EVENTS context, **Then** it writes each line verbatim on its own line before its next tool call or in its reply.

## Work Log
- 2026-11-24 [claude]: Status transitioned to complete via cos task-done.
- 2026-11-24 [claude]: The desktop app's default transcript view folds tool rows, where a PostToolUse systemMessage lands, so the user never…
