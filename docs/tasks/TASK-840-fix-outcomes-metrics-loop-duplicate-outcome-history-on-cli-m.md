---
id: TASK-840
title: "fix outcomes/metrics loop: duplicate outcome_history on CLI, missing time_to_solution metric"
swimlane: core
kind: bug
epic: null
labels: [ready]
status: in_progress
priority: P1
appetite: 1d
created: 2026-07-17
started: 2026-07-17
completed: null
agent_session: ses-claude-20260717-014556-89d0
depends_on: []
blocked_by: []
references: []
---
# TASK-840: fix outcomes/metrics loop: duplicate outcome_history on CLI, missing time_to_solution metric

**Outcome (one sentence):** cos task-done writes exactly one outcome_history row per completion (not two), and the documented drift-detection metric time_to_solution actually exists and trends the real duration_min data — restoring the "are tasks getting faster" self-assessment loop the rules reference.

## Read First
- src/cli/board_commands.py
- src/core/board_os/mcp_tools.py
- src/core/thinking_os/tools/metrics.py
- src/core/thinking_os/record_outcome.py

## Repro Steps
cos task-done → cos_task_move fires _record_completion_outcome_safe→record_outcome, then the CLI also calls _record_brain_outcome_safe→record_outcome again → 2 outcome_history rows. cos_metric_trend(metric='time_to_solution') → {'error':'Invalid metric'} because VALID_METRICS lacks it (metrics.py:21).

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a task completed via cos task-done (CLI) **When** record_outcome runs **Then** exactly one outcome_history row is appended (the CLI no longer double-records via both cos_task_move and _record_brain_outcome_safe); **And Given** cos_metric_trend(metric='time_to_solution') **When** called **Then** it returns a real trend over duration_min (not an Invalid metric error).

## Work Log
- 2026-07-17 [claude]: Edit record_outcome.py
- 2026-07-17 [claude]: Edit metrics.py
- 2026-07-17 [claude]: Edit metrics.py
- 2026-07-17 [claude]: Edit metrics.py
- 2026-07-17 [claude]: Edit metrics.py
- 2026-07-17 [claude]: Fixed 2 outcomes/metrics bugs: (1) record_outcome now skips the outcome_history append when previous_outcome==outcome…
