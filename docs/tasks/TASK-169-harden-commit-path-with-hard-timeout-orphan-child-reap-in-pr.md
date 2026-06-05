---
id: TASK-169
title: "Harden commit path with hard timeout + orphan-child reap in pre-commit"
swimlane: core
kind: bug
epic: agent-hub
labels: [ready]
status: icebox
priority: P1
appetite: "4h"
created: 2026-06-05
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-169: Harden commit path with hard timeout + orphan-child reap in pre-commit

**Outcome (one sentence):** A hung or orphaned pre-commit child can never stall the next commit (hard timeout wrapper + reap on exit).

## Read First
- docs/engineering/agent-hub-orchestration.md
- src/scripts/_pre_commit_body.sh

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
