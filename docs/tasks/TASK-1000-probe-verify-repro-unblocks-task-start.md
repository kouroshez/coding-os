---
id: TASK-1000
title: "probe: verify --repro unblocks task-start"
swimlane: infra
kind: bug
epic: null
labels: [ready]
status: archive
priority: P2
appetite: 1d
created: 2026-08-17
started: null
completed: null
agent_session: ses-claude-20260814-120316-413b
depends_on: []
blocked_by: []
references: []
---
# TASK-1000: probe: verify --repro unblocks task-start

**Outcome (one sentence):** A bug task created with --repro starts without hand-editing its body.

## Read First
- src/cli/_board_cli_lifecycle.py

## Repro Steps
1. Run cos task-create --kind bug with --repro. 2. Run cos task-start. Expected: it starts. Actual: before this change it failed DoR.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** --repro was passed, **When** task-start runs, **Then** it succeeds.

## Work Log
