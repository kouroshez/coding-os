---
id: TASK-412
title: "Retire per-Edit Work Log \u2192 git-derived, DB-backed HISTORY (token-optimized agent view)"
swimlane: infra
kind: feature
epic: null
labels: [ready]
status: archive
priority: P2
appetite: 1d
created: 2026-06-13
started: null
completed: null
agent_session: ses-claude-20260619-211916-fd8f
depends_on: []
blocked_by: []
references: []
---
# TASK-412: Retire per-Edit Work Log → git-derived, DB-backed HISTORY (token-optimized agent view)

**Outcome (one sentence):** Replace the per-Edit ## Work Log section with a git-derived, DB-backed HISTORY so the agent reads a token-optimized but technically-detailed task history; retiring the per-Edit append also removes the root cause of the stream phantom-row (TASK-411) and work-log-placement bugs. git becomes the single forensic record (consistent with the retired audit subsystem).

## Read First
- src/core/board_os/mcp_tools.py
- src/core/hooks/capture-work-log.sh
- src/core/hooks/link-commit-to-task.sh
- src/core/board_os/transition_gates_validator.py
- src/core/web/ui/src/features/cos-board/CosBoardPage.tsx
- src/core/web/routes/board.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a code Edit during an active task, **When** the edit completes, **Then** no line is appended to the task .md (capture-work-log.sh retired) and the task file mtime is unchanged.
- **Given** a commit linked to a task, **When** cos_task_history runs, **Then** the commit is sourced from an append-only task_commit_links DB table, not from grepping Work Log prose (_git_commits_from_worklog removed).
- **Given** the agent opens a task, **When** it calls cos_task_show, **Then** it receives a compact history digest (status transitions + last-N commit subjects + contributors + commit_count) and NO verbose per-Edit log; full diffs stay on-demand via the existing /commit + /diff routes.
- **Given** cos_task_create, **When** a new task is generated, **Then** its body has no ## Work Log section.
- **Given** task-done DoD, **When** require_work_log was the gate, **Then** it is replaced by a history-event check or removed, and DOD_WORK_LOG_MISSING no longer fires.
- **Given** the changes, **When** the board_os + stream + cli + ui test suites run, **Then** green; legacy tasks keep their inert ## Work Log section (one-time SHA extraction migration, no rewrite of prose).

## Work Log
- 2026-06-15 [claude]: Next-session plan (handoff): retire per-Edit Work Log -> git-derived, DB-backed HISTORY. Start by reading board_os work-
- 2026-06-15 [claude]: SCOUT VERDICT (2026-06-15): NOT a safe 1-commit change — fresh-context, 6-phase task with an IRREVERSIBLE v43 schema mig
- 2026-06-15 [claude]: P1 table task_commit_links(task_id,commit_sha,subject,author,committed_at,source,linked_at; UNIQUE(task_id,commit_sha);
- 2026-06-15 [claude]: READER: cos_task_history (mcp_tools.py:2789) drop _git_commits_from_worklog(2660)+_worklog_events(2745); SELECT from tas
