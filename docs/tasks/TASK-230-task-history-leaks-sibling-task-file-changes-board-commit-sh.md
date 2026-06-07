---
id: TASK-230
title: "Task history leaks sibling-task file changes \u2014 board_commit shows ALL files of a batched commit under one task's HISTORY"
swimlane: "board_os"
kind: bug
epic: null
labels: [board, web, ui, history, ready]
status: complete
priority: P2
appetite: 4h
created: 2026-06-07
started: 2026-06-07
completed: 2026-06-07
agent_session: ses-claude-20260606-135311-dd32
depends_on: []
blocked_by: []
references: []
---
# TASK-230: Task history leaks sibling-task file changes — board_commit shows ALL files of a batched commit under one task's HISTORY

**Outcome (one sentence):** A task's HISTORY shows only file changes relevant to THAT task: board_commit accepts an optional for_task and drops other tasks' docs/tasks/TASK-*.md from the numstat file list (keeps the task's own file + all code/doc files); the SPA CommitRow passes the open task's id as for_task. So a commit that touched 7 task files no longer renders 6 sibling files under one task's history.

## Read First
- src/core/web/routes/board.py
- src/core/web/ui/src/features/cos-board/CosBoardPage.tsx

## Repro Steps
1. Make/observe a commit that touches more than one docs/tasks/TASK-*.md in a single commit (e.g. a85a5d98 touched TASK-223..229).
2. Open any of those tasks in the web board and expand that commit under HISTORY.
Expected: only this task's own file (+ any code/doc files) is listed.
Actual: all 7 sibling task files are listed under the one task's history (cross-task leak).

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a single commit that touched multiple tasks' docs/tasks/TASK-*.md files.
- **When** a user expands that commit under one task's HISTORY (UI calls /api/board/commit/{sha}?for_task=<id>).
- **Then** board_commit drops the OTHER tasks' TASK-*.md from the file list (keeps this task's own file + all non-task/code files), the SPA threads the open task's id, and only relevant files render — verified on a known multi-task commit.

## Work Log
- 2026-06-07 [claude]: Fixed cross-task history leak. board_commit gained for_task query param; when set (validated TASK-\d+) it drops OTHER ta
