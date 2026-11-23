---
id: TASK-1098
title: "feat(hooks): show each task create and move live, one plain event per line"
swimlane: core
kind: feature
epic: workflow-enforcement
labels: [governance, ready]
status: complete
priority: P2
appetite: 1d
created: 2026-11-23
started: 2026-11-23
completed: 2026-11-23
agent_session: ses-claude-20261123-135444-89e7
depends_on: []
blocked_by: []
references: []
---
# TASK-1098: feat(hooks): show each task create and move live, one plain event per line

**Outcome (one sentence):** Right after the agent creates or moves a task, the user sees one plain line per event with the task title (for example "▶️ TASK-1100 started — Fix login crash"), and the end-of-turn Stop line only repeats nothing.

## Read First
- src/core/rules/transparency-banner.md
- src/core/hooks/_helpers/board_turn_summary.py
- src/core/hooks/warn-abandoned-task.sh
- src/core/hooks/registry.yaml

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the agent creates or moves a task through cos_task_* or a cos task-* command, **When** the tool call returns, **Then** a systemMessage shows one plain line per new event with icon, task id, plain verb and short title
- **Given** those events were shown live, **When** the turn stops, **Then** the Stop hook shows nothing for them
- **Given** an emergency task is created or a task is escalated, **When** its event is shown, **Then** the line says emergency in words with the 🚨 icon
- **Given** the hook, adapter, rules and golden suites, **When** run, **Then** they pass

## Work Log
- 2026-11-23 [claude]: Done: the helper now writes one plain sentence per event with the short title. New PostToolUse hook…
- 2026-11-23 [claude]: Status transitioned to complete via cos task-done.
