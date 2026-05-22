---
id: TASK-012
title: "Trunk-based git workflow — kill branch sprawl + concurrent-session safety"
swimlane: core
kind: feature
epic: null
labels: [governance, hooks, git-workflow]
status: complete
priority: P2
appetite: "1d"
created: 2026-05-22
started: null
completed: 2026-05-22
agent_session: ses-claude-20260522-181701-790c
depends_on: []
blocked_by: []
references: []
---
# TASK-012: Trunk-based git workflow — kill branch sprawl + concurrent-session safety

**Outcome (one sentence):** Agents commit directly to main (no feature branches). branch-guard hook blocks branch creation in trunk mode. SessionStart surfaces dirty working tree. Publish-mode config seam allows future PR mode without rewrite.

## Read First
- src/core/rules/git-workflow.md (created by this task — the SSOT)
- src/core/hooks/registry.yaml
- src/core/hooks/block-dangerous-commands.sh (guard-hook pattern)

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** an agent on the default branch in trunk mode
- **When** it runs `git checkout -b X` / `git branch X` / `git switch -c X`
- **Then** branch-guard.sh BLOCKs (exit 2) with remediation; a direct
  commit to main is allowed; `COS_GIT_WORKFLOW=pr` or explicit user
  override lets the branch through.

## Work Log

- 2026-05-22 — Implemented trunk-based workflow (Rule 23). New rule
  `src/core/rules/git-workflow.md`; `branch-guard.sh` hook BLOCKs
  branch/worktree creation in trunk mode (`COS_GIT_WORKFLOW=pr` is the
  future-team seam); `session-context.sh` surfaces a dirty working tree
  at startup. Registered in registry.yaml + codex pretool dispatcher.
  Verified: verify-hooks clean, 11 branch-guard tests, adapter+golden
  parity green. Golden regen also folds in pre-existing doc-link drift
  from da59ea5.
- 2026-05-22 [claude]: Status transitioned to complete via cos task-done.
