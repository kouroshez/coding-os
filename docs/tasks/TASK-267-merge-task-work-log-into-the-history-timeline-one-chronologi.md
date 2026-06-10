---
id: TASK-267
title: "Merge task Work Log into the History timeline (one chronological story)"
swimlane: core
kind: feature
epic: hub-redesign
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-08
started: 2026-06-08
completed: 2026-06-08
agent_session: ses-claude-618-2ab7
depends_on: []
blocked_by: []
references: []
---
# TASK-267: Merge task Work Log into the History timeline (one chronological story)

**Outcome (one sentence):** The task drawer shows ONE chronological timeline — created, status moves, edits, work-log notes, and commits interleaved — and the duplicate "## Work Log" section is dropped from the rendered body so nothing appears twice.
- 2026-06-08 [claude]: cos_task_history now emits `worklog` events parsed from the task body's Work Log bullets (date→epoch +i for same-day ord
- 2026-06-08 [claude]: committed 817a0e45: src/core/board_os/mcp_tools.py, src/core/web/ui/src/features/cos-board/CosBoardPage.tsx

## Read First
- src/core/board_os/mcp_tools.py — cos_task_history (~2274), _git_commits_* helpers
- src/core/board_os/parser.py — parse_task / work_log_lines (~130)
- src/core/web/ui/src/features/cos-board/CosBoardPage.tsx — TaskHistoryEvent (~3775), HISTORY_ICON, describe (~4024), body derivation (~3359)

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a task with Work Log bullets, **When** its history is fetched, **Then** each bullet appears as a `worklog` event in the timeline (dated, actor-attributed), interleaved chronologically with status/edit/commit events.
- **Given** the task drawer, **When** it renders the markdown body, **Then** the "## Work Log" section is no longer shown in the body (it lives only in the unified timeline), while Outcome/Read First/Acceptance/Rollback still render.
- **Given** a task with no Work Log, **When** history is fetched, **Then** no worklog events appear and existing behaviour is unchanged.

## Work Log
