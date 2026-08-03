---
id: TASK-862
title: "Declutter Hub task HISTORY panel \u2014 commits-first default, details behind a toggle"
swimlane: core
kind: feature
epic: null
labels: [hub-ui, board, ready]
status: complete
priority: P2
appetite: 1d
created: 2026-08-03
started: 2026-08-02
completed: 2026-08-02
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-862: Declutter Hub task HISTORY panel — commits-first default, details behind a toggle

**Outcome (one sentence):** TaskHistoryPanel defaults to a clean commits-only timeline (each commit clickable → files + line diffs, as today); a "Show details (N)" toggle reveals the full activity stream (created/status/edit/worklog); worklog bullets that merely echo a commit already shown are deduped and consecutive identical edit bullets are collapsed with a ×N counter. Backend cos_task_history contract unchanged.

## Read First
- src/core/web/ui/src/features/cos-board/task-history.tsx
- src/core/board_os/mcp_tools.py
- docs/engineering/hub-architecture.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** TASK-513's noisy history, **When** the panel opens, **Then** only commit rows + the summary line render, and a toggle shows the hidden-event count.
- **Given** the details toggle is clicked, **When** the timeline expands, **Then** the full chronological stream renders with commit-echo worklog bullets deduped and consecutive identical edit bullets collapsed (×N).
- **Given** the change, **When** `npm run typecheck` and `npm run lint` run in src/core/web/ui, **Then** both pass.

## Work Log
- 2026-08-03 [claude]: Edit hub-architecture.md
- 2026-08-03 [claude]: Edit task-history.tsx
- 2026-08-03 [claude]: Edit task-history.tsx
- 2026-08-03 [claude]: Edit task-history.tsx
- 2026-08-03 [claude]: Deliberation: UI-only fix (task-history.tsx) over a backend history filter — cos_task_history envelope already types…
- 2026-08-03 [claude]: Status transitioned to complete via cos task-done.
