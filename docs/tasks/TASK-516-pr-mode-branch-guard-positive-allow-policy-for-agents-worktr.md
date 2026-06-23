---
id: TASK-516
title: "pr-mode branch-guard: positive allow-policy for agents/* + worktree, keep HEAD/protected guards (replace exit 0)"
swimlane: core
kind: feature
epic: multi-agent-pr-mode
labels: [pr-mode, hooks, branch-guard, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-06-22
started: 2026-06-22
completed: 2026-06-22
agent_session: ses-claude-20260622-134704-4de9
depends_on: [TASK-515]
blocked_by: []
references: []
---
# TASK-516: pr-mode branch-guard: positive allow-policy for agents/* + worktree, keep HEAD/protected guards (replace exit 0)

**Outcome (one sentence):** COS_GIT_WORKFLOW=pr stops being a global guard-kill (branch-guard.sh:43 exit 0). branch_guard_check.py gains a positive pr-mode policy: allow agents/* branch-create + worktree-add into the worktree root, while still BLOCKING reset/rebase/HEAD-move on the shared integration checkout and any op on a protected branch. Additionally, in pr-mode the guard BLOCKS `git commit` (and a companion PreToolUse Write|Edit check blocks file edits) on the shared integration checkout itself — so EVERY code change, even work the user explicitly said not to make a board task for, is forced into an isolated worktree, never the shared tree. The misleading inline-override _MSG is corrected to point at the persisted-env mechanism.

## Read First
- src/core/hooks/branch-guard.sh
- src/core/hooks/_helpers/branch_guard_check.py
- src/core/rules/git-workflow.md
- src/core/hooks/block-dangerous-commands.sh

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** COS_GIT_WORKFLOW=pr, **When** the agent runs `git checkout -b agents/<task>/<id>` or `git worktree add <worktree-root>/...`, **Then** it is allowed. **Given** COS_GIT_WORKFLOW=pr, **When** the agent runs `git reset HEAD~3` / `git rebase` on the shared integration checkout or any write op targeting a protected branch, **Then** it is BLOCKED with a remediation message. **Given** COS_GIT_WORKFLOW=pr and cwd is the shared integration checkout (not a worktree), **When** the agent attempts `git commit` or a Write/Edit on repo files, **Then** it is BLOCKED with "create/enter a worktree first (cos pr open)". **Given** tests/test_branch_guard.py new pr-mode policy cases plus `make verify-hooks`, **Then** green.

## Work Log
- 2026-06-23 [claude]: branch_guard_check.py: pr-mode is now a positive policy (not exit 0) — allow agents/* branches + worktree-add, block…
