---
id: TASK-1113
title: "fix(board): task create keeps the sections the caller gave even when the kind does not require them"
swimlane: "board_os"
kind: bug
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-11-24
started: 2026-11-24
completed: 2026-11-24
agent_session: ses-claude-20261124-115753-d372
depends_on: []
blocked_by: []
references: []
---
# TASK-1113: fix(board): task create keeps the sections the caller gave even when the kind does not require them

**Outcome (one sentence):** cos_task_create renders Read First, Acceptance and Repro Steps whenever the caller passes them, so a chore created with acceptance keeps it and its automatic review receives acceptance criteria.

## Read First
- src/core/board_os/_mcp_create.py
- src/core/board_os/transition-gates.yaml

## Repro Steps
cos_task_create(kind='chore', acceptance='- **Given** ...', read_first=[...]) produced TASK-1111 with only Outcome and Work Log: _render_body adds a section only when the kind's DoR lists it, so both were dropped silently, the review package had no acceptance criteria, and task-done warned DOD_ACCEPTANCE_MISSING.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** kind chore with acceptance and read_first passed, **When** the task is created, **Then** both sections are in the task file with the given content.
- **Given** a kind whose DoR requires a section the caller did not pass, **When** the task is created, **Then** the placeholder is still rendered as before.
- **Given** kind chore without acceptance, **When** the task is created, **Then** no empty Acceptance placeholder is added.

## Work Log
- 2026-11-24 [claude]: commit 46ac6d6e9f — fix(board): task create keeps the sections the caller gave even when the kind does not require them
- 2026-11-24 [claude]: Review round 1 passed, 2 lows accepted: Repro Steps on a chore follows the same tested pattern as Acceptance;…
- 2026-11-24 [claude]: Status transitioned to complete via cos task-done.
