---
id: TASK-015
title: "branch-guard — block git rebase on trunk"
swimlane: core
kind: feature
epic: null
labels: [governance, hooks, hardening, post-TASK-014]
status: archive
priority: P2
appetite: "1d"
created: 2026-05-23
started: null
completed: 2026-05-22
agent_session: ses-claude-20260522-181701-790c
depends_on: [TASK-014]
blocked_by: []
references: []
---
# TASK-015: branch-guard — block git rebase on trunk

**Outcome (one sentence):** branch-guard.sh blocks git rebase (history-rewrite onto main) while still allowing safe cleanup forms (--abort/--continue/--skip/--quit/--edit-todo/--show-current-patch) and the unrelated `git pull --rebase` workflow. Closes the most enterprise-relevant gap left after TASK-014.

## Read First
- src/core/hooks/_helpers/branch_guard_check.py
- tests/test_branch_guard.py
- src/core/rules/git-workflow.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** branch-guard in trunk mode
- **When** the agent runs `git rebase main`, `git rebase -i HEAD~3`,
  `git rebase origin/main`, or `git rebase` (bare → defaults to upstream)
- **Then** branch-guard BLOCKs (exit 2) with a remediation message
  pointing to `git revert HEAD` for safe undo.
- **And** the following remain allowed: `git rebase --abort`,
  `git rebase --continue`, `git rebase --skip`, `git rebase --quit`,
  `git rebase --edit-todo`, `git rebase --show-current-patch`,
  `git pull --rebase origin main` (subcmd is `pull`, not `rebase`).
- **And** `COS_GIT_WORKFLOW=pr` allows all forms (the seam).
- **And** previous 51 tests stay green.

## Scope (Rule 22 — OUT)
- `git cherry-pick` — creates new commit, safe-ish on trunk; defer.
- `git commit --amend` — local-only common; defer (force-push after
  amend is already caught by block-dangerous-commands).
- `eval` / `xargs` constructed git commands — out of static-analysis
  threat model.

## Work Log

- 2026-05-23 — Added `_check_rebase` to the branch_guard dispatch.
  Cleanup forms (`--abort/--continue/--skip/--quit/--edit-todo/
  --show-current-patch`) remain allowed; every other invocation blocks
  with a remediation message pointing to `git pull --rebase origin main`
  (the legit integration form) and `git revert HEAD` (the legit undo).
  13 new tests: 4 block (onto main, `-i`, onto remote, bare) + 5 allow
  (4 cleanup flags + show-current-patch) + 2 nested (via `git -C` and
  `sh -c`) + 1 `git pull --rebase` regression + 1 pr-mode seam. Total
  64 tests pass. git-workflow.md updated with the rebase rule. Adapter
  + golden parity green.
- 2026-05-23 [claude]: Status transitioned to complete via cos task-done.
