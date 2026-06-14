---
id: TASK-415
title: "Scheduled dependency-readiness reconciler \u2014 re-block reopened deps + surface unblocked-but-unauthored (TASK-414 follow-up)"
swimlane: "board_os"
kind: feature
epic: null
labels: [board_os, autonomous, dependencies, follow-up]
status: icebox
priority: P3
appetite: 1d
created: 2026-06-14
started: null
completed: null
agent_session: null
depends_on: [TASK-414]
blocked_by: []
references: []
---

# TASK-415: Scheduled dependency-readiness reconciler — re-block reopened deps + surface unblocked-but-unauthored (TASK-414 follow-up)

**Outcome (one sentence):** A nightly reconciler that closes the gaps the per-completion cascade (TASK-414 slice B) cannot cover: (1) move a ready/icebox task back to blocked when a previously-complete dependency reopens or is reverted; (2) surface tasks now dependency-unblocked but DoR-incomplete (needs-authoring) and tasks blocked beyond N days — so the board self-heals across the whole graph, not only at the moment a single dependency completes.

## Read First
- src/core/scheduled/nightly.py
- src/core/board_os/mcp_tools.py
- docs/governance/task-lifecycle.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a ready/icebox task whose dependency transitions from complete back to a non-complete status, **When** the nightly reconciler runs, **Then** the task is moved to blocked with a reason naming the reopened dependency. - **Given** a task whose dependencies are all complete but whose DoR body is incomplete, **When** the reconciler runs, **Then** it is reported in a needs-authoring list (not auto-readied, not silently hidden). - **Given** a task blocked longer than the configured threshold, **When** the reconciler runs, **Then** it is surfaced for human review. - **Given** the changes, **When** the board_os + scheduled-job suites run, **Then** green with new tests for each branch.

## Work Log
