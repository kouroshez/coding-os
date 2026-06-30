---
id: TASK-664
title: "Force-complete requires an audited reason \u2014 gate workflow.transition(force=True) through evaluate_override"
swimlane: "board_os"
kind: feature
epic: task-lifecycle-integrity
labels: [dod, force, audit, ready]
status: icebox
priority: P1
appetite: 1d
created: 2026-06-30
started: null
completed: null
agent_session: null
depends_on: [TASK-662]
blocked_by: []
references: []
---

# TASK-664: Force-complete requires an audited reason — gate workflow.transition(force=True) through evaluate_override

**Outcome (one sentence):** workflow.transition(force=True) no longer silently drops BOTH the testing-route gate and the DoD gate with zero reason — a forced complete routes through evaluate_override and is rejected unless COS_OVERRIDE_REASON (>=15 chars) is supplied, so every gate bypass is audited exactly like the transition_gates_cli path already is.

## Read First
- src/core/board_os/workflow.py
- src/core/board_os/transition_gates_validator.py
- docs/governance/task-lifecycle.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a force=True complete with no override reason, **When** workflow.transition runs, **Then** the bypass is rejected and an OVERRIDE_REASON_MISSING-class message is surfaced.
- **Given** a force=True complete with a >=15-char COS_OVERRIDE_REASON, **When** it runs, **Then** the bypass proceeds and the reason is recorded to the override audit sink.
- **Given** a normal non-force complete, **When** it runs, **Then** behavior is unchanged (no regression).

## Work Log
