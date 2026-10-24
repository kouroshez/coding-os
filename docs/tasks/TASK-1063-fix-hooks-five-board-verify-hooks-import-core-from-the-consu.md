---
id: TASK-1063
title: "fix(hooks): five board/verify hooks import core from the consumer root and never run there"
swimlane: core
kind: bug
epic: null
labels: [ready]
status: complete
priority: P0
appetite: 1d
created: 2026-10-24
started: 2026-10-24
completed: 2026-10-24
agent_session: ses-claude-20261024-131905-031f
depends_on: []
blocked_by: []
references: []
---
# TASK-1063: fix(hooks): five board/verify hooks import core from the consumer root and never run there

**Outcome (one sentence):** enforce-task-body, enforce-verify, test-governor, record-verify and record-verify-auto run their Python checks in every consumer project instead of failing with ModuleNotFoundError, and a failed check is never logged as block.

## Read First
- docs/engineering/hooks-reference.md

## Repro Steps
1. `cd ~/Files/Project/streamos`
2. `echo '{"tool_name":"Write","tool_input":{"file_path":"docs/tasks/TASK-999-x.md","content":"x"}}' | COS_AGENT=claude bash .claude/hooks/enforce-task-body.sh`
3. → `ModuleNotFoundError: No module named 'core'`, exit 1, logged as `[block]`.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a consumer project with no `core` package on its path **When** enforce-task-body receives a task Write **Then** the transition gate CLI runs (no ModuleNotFoundError)
- **Given** the Python runner itself cannot start **When** the hook exits **Then** the log says error, not block

## Work Log
- 2026-10-24 [claude]: Status transitioned to complete via cos task-done.
