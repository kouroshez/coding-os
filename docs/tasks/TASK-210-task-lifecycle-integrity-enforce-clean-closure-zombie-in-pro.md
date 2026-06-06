---
id: TASK-210
title: "Task-lifecycle integrity \u2014 enforce clean closure (zombie in_progress/testing, icebox pileup, no SessionEnd hook, exhaustive-only guardian)"
swimlane: core
kind: bug
epic: task-lifecycle-integrity
labels: [workflow-integrity, board, hooks, lifecycle, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-06-06
started: 2026-06-05
completed: 2026-06-06
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-210: Task-lifecycle integrity — enforce clean closure (zombie in_progress/testing, icebox pileup, no SessionEnd hook, exhaustive-only guardian)

**Outcome (one sentence):** Agents can no longer silently abandon tasks. Every started task reaches a terminal state or is auto-reclaimed; zombie in_progress AND testing are detected and surfaced as real pressure (not a one-shot warning scoped to the live session); inherited zombies from dead sessions get an action path, not just a banner; the Stop guardian covers ordinary task closure (not only exhaustive-intent audits); icebox accumulation gets a hygiene/triage loop. Enterprise-grade, Claude-adapter-first, propagates cleanly to consumers via core symlinks.

## Read First
- src/core/thinking_os/completion_guardian.py
- src/core/hooks/warn-abandoned-task.sh
- src/core/hooks/registry.yaml
- src/core/board_os/workflow.py
- src/core/rules/auto-mode-vs-exhaustive.md

## Repro Steps
1. `cos task-start TASK-X`; make edits; run a turn; do NOT call `task-done`; end or kill the session.
2. Next `cos board` shows TASK-X stranded in `in_progress`/`testing` under a now-dead session.
3. No Stop hook blocks the abandonment (guardian is exhaustive-intent-only); `cos task-reclaim` + `warn-abandoned-task` are `in_progress`-only so a `testing` zombie is invisible; `SessionEnd` has zero hooks so a hard kill runs nothing.

Expected: a started task reaches a terminal state or is auto-reclaimed within the configured idle window; rot is visible on every board surface.
Actual: TASK-100 sat in `testing` ~9 days under a dead session; 40/41 tasks rot in `icebox`; closure is enforced by nothing for ordinary tasks. (Audit: docs/tasks/audits/audit-task-lifecycle-integrity-2026-06-05.md)

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a stale `testing`/`in_progress` task owned by an inactive session, **When** the reclaim sweep runs (SessionStart or nightly), **Then** it is reclaimed within the per-status idle window (testing→in_progress+ready, in_progress→icebox+ready) and surfaced in `cos daily`.
- **Given** a session that started a task and produced edits, **When** it tries to Stop without closing it, **Then** the guardian (keyed on `.task-current` ∩ DB status) escalates warn→block under `COS_ENFORCE_TASK_CLOSURE=strict`, with `blocked`/`.leave-open` escapes; fail-open on DB error.
- **Given** any board read (board/daily/retro/hub), **When** a card is rendered, **Then** it carries `status_dwell_seconds` and a `stale` flag past its per-status SLA.
- **Given** `cos task-archive TASK-N`, **When** invoked, **Then** the task moves to the terminal `archive` status (the verb exists; icebox has a real drain).
- **Then** matrix verification is green for every changed layer AND the audit reviewer subagent re-grep returns 0.

## Work Log
- 2026-06-06 [claude]: committed 8152c349: docs/tasks/audits/audit-task-lifecycle-integrity-2026-06-05.md
- 2026-06-06 [claude]: Status transitioned to complete via cos task-done.
