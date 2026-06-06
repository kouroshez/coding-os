---
id: TASK-175
title: "Commit-to-task-log write-back via post-commit hook"
swimlane: core
kind: feature
epic: agent-hub
labels: [ready]
status: complete
priority: P2
appetite: "4h"
created: 2026-06-05
started: 2026-06-05
completed: 2026-06-05
agent_session: ses-claude-20260605-183120-db30
depends_on: []
blocked_by: []
references: []
---
# TASK-175: Commit-to-task-log write-back via post-commit hook

**Outcome (one sentence):** A git post-commit hook detects the task from the committed `docs/tasks/TASK-NNN-*.md` file and appends one idempotent, fail-open Work Log line listing the committed code files + short sha to that task.

## Read First
- docs/engineering/agent-hub-orchestration.md
- src/scripts/install-git-hooks.sh
- src/core/hooks/capture-work-log.sh

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a commit that includes a task's `TASK-NNN-*.md` plus code files
- **When** the post-commit hook runs
- **Then** it appends exactly one Work Log line to TASK-NNN ("committed <sha8>: file1, file2 …"), is idempotent per sha, never fails the commit (fail-open), and is installed by install-git-hooks.sh. A bash test covers detection + idempotency; bash -n + shellcheck clean.

## Work Log
- 2026-06-06 [claude]: Added src/scripts/_post_commit_body.sh: detects the task from the committed TASK-NNN.md, appends an idempotent fail-open
