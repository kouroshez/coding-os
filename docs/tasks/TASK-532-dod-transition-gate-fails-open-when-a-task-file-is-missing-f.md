---
id: TASK-532
title: "DoD transition gate fails OPEN when a task file is missing \u2014 fail-closed + re-materialize TASK-523/524/525"
swimlane: "board_os"
kind: bug
epic: pr-mode-hardening
labels: [board, dod-gate, ssot, ready]
status: icebox
priority: P2
appetite: 1d
created: 2026-06-23
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-532: DoD transition gate fails OPEN when a task file is missing — fail-closed + re-materialize TASK-523/524/525

**Outcome (one sentence):** A complete-transition can never be cheaper than one with a present file: when to_status==complete and the task file is absent, the DoD gate BLOCKs ('task file not found — cannot verify DoD') instead of skipping the whole verify block; and the three hardening tasks TASK-523/524/525 (DB rows with no file) are re-materialized from their DB goal_text + work_log via the cos write path and committed, ending the board↔docs SSOT desync.

## Read First
- src/core/board_os/workflow.py
- docs/governance/task-lifecycle.md

## Repro Steps
A task with status=complete in the DB but no docs/tasks/TASK-NNN.md on disk (e.g. 523/524/525) closed testing→complete in ~4-7s; workflow.py:542 `if target_file_for_gate.exists():` wraps the whole DoD block, so the absent file skipped the verify-freshness gate entirely.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a task whose file is absent and to_status==complete **When** cos_task_move runs **Then** it BLOCKs naming the missing file (no silent skip).
- **Given** TASK-523/524/525 **When** the fix lands **Then** their docs/tasks/*.md exist on disk, are committed, and cos_task_show renders them.
- **And** `uv run --extra rag --with aiohttp --with pytest-asyncio pytest src/core/board_os/tests/ -q` is green.

## Work Log
