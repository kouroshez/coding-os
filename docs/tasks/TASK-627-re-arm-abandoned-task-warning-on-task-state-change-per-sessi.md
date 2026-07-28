---
id: TASK-627
title: "Re-arm abandoned-task warning on task-state-change (per-session debounce went silent)"
swimlane: core
kind: bug
epic: null
labels: [ready]
status: archive
priority: P2
appetite: 1d
created: 2026-06-27
started: 2026-06-27
completed: 2026-06-27
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-627: Re-arm abandoned-task warning on task-state-change (per-session debounce went silent)

**Outcome (one sentence):** warn-abandoned-task.sh keys its Stop-hook debounce on (session-id, current-open-task-set) instead of session-id alone, so the nudge re-fires when the open-task set changes (a task moved in_progress->testing, or one closed and another opened) — catching the "85%-done then stopped" abandonment that the once-per-session debounce went silent on — while still suppressing identical repeat warnings within an unchanged state (no alarm fatigue).

## Read First
- src/core/hooks/warn-abandoned-task.sh

## Repro Steps
Audit 2026-06: warn-abandoned-task.sh:34-38 debounces on SESSION_ID substring only; once warned, a session never re-warns even after the task progresses (in_progress->testing) and is then abandoned near-done — the exact "85% then stopped" pattern the hook exists to catch is invisible after the first warning.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a session was already warned about TASK-X in_progress **When** TASK-X moves to testing and the session stops again without closing it **Then** the hook re-warns (the open-task signature changed). - **Given** the open-task set is unchanged since the last warning **When** the session stops again **Then** the hook stays silent (debounced, no alarm fatigue). - **Given** no task is open for the session **When** it stops **Then** no warning and no marker write.

## Work Log
- 2026-06-27 [claude]: Edit warn-abandoned-task.sh
- 2026-06-27 [claude]: Edit test_warn_abandoned_task.py
- 2026-06-27 [claude]: committed 50f41d50 · 8 files
