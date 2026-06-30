---
id: TASK-714
title: "[board-drift] 38 untracked / 9 modified / 1 missing task file(s)"
swimlane: infra
kind: chore
epic: null
labels: [auto-git-drift, board-coherence, ready]
status: icebox
priority: P2
appetite: 1d
created: 2026-06-30
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-714: [board-drift] 38 untracked / 9 modified / 1 missing task file(s)

**Outcome (one sentence):** board↔git drift — 38 untracked, 9 modified, 1 missing .md (DB row without a committed file) — commit the untracked/modified docs/tasks/*.md (or reconcile the DB rows) so the board (DB) and git agree.

## Read First
- docs/governance/task-lifecycle.md
- src/core/board_os/git_coherence.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** board↔git drift (untracked/modified/missing docs/tasks/*.md) **When** the drifted files are committed (or the orphaned DB rows reconciled) **Then** `cos doctor` board.git_tracked reports no drift.

## Work Log
