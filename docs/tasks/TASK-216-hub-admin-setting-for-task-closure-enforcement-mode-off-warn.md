---
id: TASK-216
title: "Hub admin setting for task-closure enforcement mode (off/warn/strict) \u2014 UI-visible + configurable + described"
swimlane: core
kind: feature
epic: task-lifecycle-integrity
labels: [workflow-integrity, hub, ui, lifecycle, ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-06
started: 2026-06-06
completed: 2026-06-06
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-216: Hub admin setting for task-closure enforcement mode (off/warn/strict) — UI-visible + configurable + described

**Outcome (one sentence):** The task-closure enforcement mode (off/warn/strict) is visible and settable from the Hub admin Settings page, with a short in-panel explanation. The completion guardian resolves the mode as: COS_ENFORCE_TASK_CLOSURE env var (override, wins) -> hub-settings.json task_closure.mode (set by the UI) -> warn (default). So a shell export still wins for power users, while everyone else configures it from the web panel — web panel stays aligned with core.

## Read First
- src/core/web/routes/settings.py
- src/core/web/ui/src/pages/SettingsPage.tsx
- src/core/thinking_os/completion_guardian.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the Hub Settings page, **When** an admin opens it, **Then** a "Task-Closure Enforcement" section shows a mode selector (off/warn/strict) with a short explanation of each mode, and an env-override badge when `COS_ENFORCE_TASK_CLOSURE` is set.
- **Given** the admin sets mode=strict and saves, **When** `hub-settings.json` is written, **Then** the completion guardian resolves mode=strict from the file (no env var needed) and blocks an unclosed task at the second Stop.
- **Given** `COS_ENFORCE_TASK_CLOSURE` is exported in the shell, **When** the guardian resolves the mode, **Then** the env var WINS over the file value (and the UI shows the override badge).
- **Given** no env var and no file setting, **When** the guardian runs, **Then** mode defaults to `warn` (never blocks).
- **Then** matrix verification green (thinking_os + web + ui-build) and a reviewer confirms env-over-file precedence.

## Work Log
- 2026-06-06 [claude]: committed a1578e6c: src/core/thinking_os/completion_guardian.py, src/core/thinking_os/tests/test_completion_guardian.py,
- 2026-06-06 [claude]: Status transitioned to complete via cos task-done.
