---
id: TASK-1097
title: "feat(hooks): show this session's board transitions to the user and the task status in the banner"
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
# TASK-1097: feat(hooks): show this session's board transitions to the user and the task status in the banner

**Outcome (one sentence):** At the end of every turn the user sees which tasks this session created or moved (any status, emergency marked), and every banner and pulse states the bound task with its live status plus the open emergency count, read from the board DB.

## Read First
- src/core/rules/transparency-banner.md
- docs/governance/task-lifecycle.md
- src/core/hooks/warn-abandoned-task.sh
- src/core/hooks/_session_pulse.sh
- src/adapters/codex/hooks/codex-merge-hook-output.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a turn in which this session created or moved tasks, **When** the turn stops, **Then** a systemMessage lists each task's status chain from task_status_history once, marking emergency, and a repeated Stop does not report it again
- **Given** a bound task, **When** the next prompt is submitted, **Then** the banner and pulse show task=<ID>·<status> and an emergency=N segment when open emergency tasks exist
- **Given** the Codex Stop dispatcher, **When** a delegate returns only a systemMessage, **Then** the merged output carries it as systemMessage and adds no additionalContext
- **Given** the hook, adapter, rules and golden suites, **When** run, **Then** they pass

## Work Log
- 2026-11-23 [claude]: Plan: extend the existing Stop hook warn-abandoned-task.sh (already resolves the session, reads task_status_history,…
- 2026-11-23 [claude]: Done: warn-abandoned-task.sh now emits a systemMessage with this session's status chains since the per-panel…
- 2026-11-23 [claude]: Status transitioned to complete via cos task-done.
