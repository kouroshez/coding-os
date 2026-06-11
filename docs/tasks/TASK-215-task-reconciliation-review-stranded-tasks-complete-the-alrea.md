---
id: TASK-215
title: "Task reconciliation \u2014 review stranded tasks, complete the already-done; don't blindly recycle; periodic archive of completed"
swimlane: core
kind: feature
epic: task-lifecycle-integrity
labels: [workflow-integrity, board, lifecycle, reconciliation, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-06-06
started: 2026-06-06
completed: 2026-06-06
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-215: Task reconciliation — review stranded tasks, complete the already-done; don't blindly recycle; periodic archive of completed

**Outcome (one sentence):** Stranded/forgotten tasks are intelligently triaged, not mechanically recycled. The system computes completion evidence per stranded task (git commits referencing the TASK-ID + work-log + whether it reached testing), classifies likely-complete vs likely-abandoned vs needs-review, and surfaces them so an agent REVIEWS and moves the already-done ones to complete (no blind auto-complete — a wrong "done" is worse than an open task). The auto-reclaim sweep no longer blindly recycles a likely-complete testing task back to in_progress — it leaves it for review. Completed tasks get periodic archive (complete→archive). Enterprise, world-class, not superficial.

## Read First
- src/core/board_os/mcp_tools.py
- src/core/hooks/reclaim-sweep.sh

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a stranded `testing` task whose owner session is dead AND that has git commits referencing its TASK-ID, **When** reconciliation runs, **Then** it is classified `likely_complete` with its evidence (commit count, dwell, work-log) and surfaced with a "review & cos task-done" recommendation — NOT auto-completed and NOT recycled to in_progress.
- **Given** a stranded `in_progress` task with zero commits and empty work-log, **When** reconciliation runs, **Then** it is classified `likely_abandoned` and recommended for cancel/park or resume.
- **Given** `cos_task_reclaim` runs over a `likely_complete` stranded task, **When** the sweep executes, **Then** that task is SKIPPED (left in testing for review) while genuinely-abandoned tasks are still reclaimed.
- **Given** `cos task-reconcile` (CLI) / `cos_task_reconcile` (MCP), **When** invoked, **Then** it returns each stranded task with classification + evidence + recommendation, and never mutates state on its own (review-first).
- **Then** matrix verification green (board_os + cli) and a reviewer confirms no blind auto-complete path exists.

## Work Log
- 2026-06-06 [claude]: Status transitioned to complete via cos task-done.
