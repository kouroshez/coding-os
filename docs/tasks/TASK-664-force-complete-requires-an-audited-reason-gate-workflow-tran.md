---
id: TASK-664
title: "Force-complete requires an audited reason \u2014 gate workflow.transition(force=True) through evaluate_override"
swimlane: "board_os"
kind: feature
epic: task-lifecycle-integrity
labels: [dod, force, audit]
status: archive
priority: P1
appetite: 1d
created: 2026-06-30
started: null
completed: null
agent_session: ses-claude-20260628-125542-fc9a
depends_on: [TASK-662]
blocked_by: []
references: []
---
# TASK-664: Force-complete requires an audited reason — gate workflow.transition(force=True) through evaluate_override

**Outcome (one sentence):** workflow.transition(force=True) no longer silently drops BOTH the testing-route gate and the DoD gate with zero reason — a USER-initiated forced complete routes through evaluate_override and is rejected unless COS_OVERRIDE_REASON (>=15 chars) is supplied, so every user gate-bypass is audited exactly like the transition_gates_cli path already is.

## Read First
- src/core/board_os/workflow.py
- src/core/board_os/mcp_tools.py
- src/core/board_os/transition_gates_validator.py
- docs/governance/task-lifecycle.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a user force=True complete with no override reason, **When** workflow.transition runs, **Then** the bypass is rejected and an OVERRIDE_REASON_MISSING-class message is surfaced.
- **Given** a user force=True complete with a >=15-char COS_OVERRIDE_REASON, **When** it runs, **Then** the bypass proceeds and the reason is recorded to the override audit sink.
- **Given** a programmatic system sweep (reclaim/archive/claim_next) that uses force, **When** it runs, **Then** it is exempt from the reason requirement and does not break.

## Implementation Guards (verified blast-radius)
- The reason requirement must be scoped to USER-initiated force (CLI/MCP `--force`) only. The programmatic sweeps cos_task_reclaim (mcp_tools.py:1946), _archive_stale_sweep (:2068) and cos_task_claim_next (:2187) also call workflow.transition — if any pass force=True they MUST be exempt (system actor), else the reaper/archiver break. Confirm each caller's force usage first.

## Work Log
