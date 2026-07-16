---
id: TASK-273
title: "Link code commits to their task via a SHA-to-Work-Log PostToolUse hook"
swimlane: core
kind: feature
epic: hub-redesign
labels: [ready]
status: archive
priority: P1
appetite: 1d
created: 2026-06-08
started: 2026-06-08
completed: 2026-06-09
agent_session: ses-claude-20260609-151118-a8c3
depends_on: []
blocked_by: []
references: []
---
# TASK-273: Link code commits to their task via a SHA-to-Work-Log PostToolUse hook

**Outcome (one sentence):** After a git commit, the new HEAD SHA is appended to the active task's Work Log, so cos_task_history surfaces the real code commits (not just the commits that touched the task .md) — fixing tasks that show only their record-done commit.

## Read First
- src/core/hooks/capture-work-log.sh — active-task resolution + work_log_append helper
- src/core/hooks/_helpers/work_log_append.py — append mechanism
- src/core/hooks/registry.yaml — hook registration (PostToolUse Bash)
- src/core/board_os/mcp_tools.py — _git_commits_from_worklog (consumes the SHA)

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** an active .task-current and a successful `git commit`, **When** the PostToolUse Bash hook fires, **Then** the task's Work Log gains a `commit <sha> — <subject>` line and cos_task_history then lists that commit.
- **Given** the same HEAD sha already recorded in the task, **When** a later/no-op commit fires the hook, **Then** it is not appended twice (dedup by grep).
- **Given** no active task or a non-commit Bash command, **When** the hook fires, **Then** it is a no-op (fail-open, exit 0).

## Work Log
- 2026-06-08 [claude]: Added src/core/hooks/link-commit-to-task.sh (PostToolUse Bash): on a real `git commit`, resolves the active .task-curren
- 2026-06-08 [claude]: STOOD DOWN: a concurrent agent is already shipping a commit→Work Log linker (the `committed <sha>: <files>` lines appear
- 2026-06-09 [claude]: Root cause: the existing git post-commit linker (TASK-175, _post_commit_body.sh) only links a commit when it BUNDLES the
