---
id: TASK-940
title: "feat: enforce the documented 300-line file budget instead of warning at 400"
swimlane: core
kind: feature
epic: null
labels: [ready]
status: icebox
priority: P2
appetite: 1d
created: 2026-08-12
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-940: feat: enforce the documented 300-line file budget instead of warning at 400

**Outcome (one sentence):** A file crossing the documented 300-line preferred budget produces a visible signal at write time, so the number in anti-overengineering.md is the number the agent actually feels.

## Read First
- src/core/hooks/block-bad-patterns.sh
- src/core/rules/anti-overengineering.md
- tests/test_file_size_budget.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a new source file of 320 lines **When** the agent writes it **Then** block-bad-patterns.sh emits a non-blocking notice naming the 300-line budget and the extraction question. **Given** a file at 505 lines **When** the agent writes it **Then** the existing hard block still fires unchanged. **Given** a generated or vendored path **When** it exceeds 300 **Then** no notice fires.

## Work Log
