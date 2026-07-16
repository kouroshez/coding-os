---
id: TASK-297
title: "Commit-to-task linking that actually works: surface git-log --grep TASK-id in task history + auto-stamp task id into commit messages (Hub + terminal + human)"
swimlane: core
kind: feature
epic: hub-redesign
labels: [hub, git, task-history, ready]
status: archive
priority: P1
appetite: 1d
created: 2026-06-09
started: 2026-06-09
completed: 2026-06-09
agent_session: ses-claude-20260609-151118-a8c3
depends_on: []
blocked_by: []
references: []
---
# TASK-297: Commit-to-task linking that actually works: surface git-log --grep TASK-id in task history + auto-stamp task id into commit messages (Hub + terminal + human)

**Outcome (one sentence):** Opening any task in the panel shows every commit that did its work — derived from the task id in the commit message (retroactive, actor-agnostic), with the id auto-stamped into commits so the link is reliable regardless of who committed.

## Read First
- src/core/board_os/mcp_tools.py
- src/scripts/_post_commit_body.sh
- src/scripts/install-git-hooks.sh
- src/core/web/routes/cognition.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a commit whose message contains `TASK-NNN`, **When** the task drawer / cos_task_history is opened, **Then** that commit is listed — retroactively, regardless of whether it touched the task .md or who committed it (`git log --all --grep`).
- **Given** an active task (.task-current=TASK-NNN), **When** any `git commit` runs (terminal or human), **Then** a `prepare-commit-msg` git hook stamps `(TASK-NNN)` into the message when it is missing, so the link is automatic.
- **Given** a Hub chat opened from a task drawer, **When** that session commits, **Then** the active task id is available so the same stamping applies (or the system prompt instructs the id be included).
- **Given** any of the above, **When** cos_task_history dedups, **Then** each commit appears once across the path / work-log / message-grep sources.

## Work Log
- 2026-06-09 [claude]: Principled commit→task linking. READ side: cos_task_history now merges _git_commits_by_task_id (git log --all --grep TAS
