---
id: TASK-170
title: "Auto-retry git index.lock collisions for concurrent commits"
swimlane: core
kind: feature
epic: agent-hub
labels: [ready]
status: icebox
priority: P2
appetite: "4h"
created: 2026-06-05
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-170: Auto-retry git index.lock collisions for concurrent commits

**Outcome (one sentence):** Concurrent commits racing index.lock retry automatically (bounded, only on the specific lock error, never blind-delete) instead of failing hard.

## Read First
- docs/engineering/agent-hub-orchestration.md
- src/core/rules/git-workflow.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** ...
- **When** ...
- **Then** ...

## Work Log
