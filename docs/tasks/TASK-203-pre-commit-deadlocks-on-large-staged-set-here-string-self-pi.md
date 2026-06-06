---
id: TASK-203
title: "pre-commit deadlocks on large staged set \u2014 here-string self-pipe write blocks (bash 5.x heredoc)"
swimlane: core
kind: bug
epic: null
labels: [git, hooks, deadlock, ready]
status: icebox
priority: P1
appetite: 1d
created: 2026-06-06
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-203: pre-commit deadlocks on large staged set — here-string self-pipe write blocks (bash 5.x heredoc)

**Outcome (one sentence):** .git/hooks/pre-commit no longer deadlocks when the staged set is large: the FILE_ARGS array is built via process substitution (drained line-by-line) instead of a `done <<< "$STAGED_FILES"` here-string whose self-pipe write blocks once the list exceeds the pipe buffer. Guarded by tests/test_pre_commit_no_deadlock.py.

## Read First
- src/scripts/_pre_commit_body.sh
- src/core/rules/git-workflow.md

## Repro Steps
1. (fill in: exact steps to reproduce)
2. ...
Expected: ...
Actual: ...

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** ...
- **When** ...
- **Then** ...

## Work Log
