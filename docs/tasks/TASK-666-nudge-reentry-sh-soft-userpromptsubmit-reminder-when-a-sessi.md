---
id: TASK-666
title: "nudge-reentry.sh \u2014 soft UserPromptSubmit reminder when a session starts new work holding an unbound in_progress task"
swimlane: core
kind: feature
epic: task-lifecycle-integrity
labels: [hooks, reentry, abandonment, ready]
status: archive
priority: P1
appetite: 1d
created: 2026-06-30
started: 2026-06-30
completed: 2026-06-30
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-666: nudge-reentry.sh — soft UserPromptSubmit reminder when a session starts new work holding an unbound in_progress task

**Outcome (one sentence):** A new nudge-reentry.sh UserPromptSubmit hook softly reminds the agent, once per (session, open-set), when it begins a new prompt while holding an in_progress task not bound to .task-current — closing the re-entry blind spot the Stop-time warn-abandoned-task (TASK-627) cannot cover, fail-open and never blocking.

## Read First
- src/core/hooks/warn-abandoned-task.sh
- src/core/hooks/session-context.sh
- src/core/hooks/registry.yaml
- docs/playbooks/hook-authoring.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a session with an in_progress task not bound to .task-current, **When** a new UserPromptSubmit arrives, **Then** nudge-reentry emits a one-line additionalContext reminder and exits 0 (never blocks).
- **Given** the same unchanged open-set, **When** subsequent prompts arrive, **Then** the nudge is debounced so there is no alarm fatigue.
- **Given** no in_progress task or a correctly-bound one, **When** a prompt arrives, **Then** the hook stays silent.

## Work Log
- 2026-07-01 [claude]: Added nudge-reentry.sh (UserPromptSubmit twin of warn-abandoned-task, session-scoped, debounced); registered;…
- 2026-07-01 [claude]: committed 94eb7b2d · 18 files
- 2026-07-01 [claude]: Status transitioned to complete via cos task-done.
