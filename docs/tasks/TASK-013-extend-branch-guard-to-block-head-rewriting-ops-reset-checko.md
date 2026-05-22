---
id: TASK-013
title: "Extend branch-guard to block HEAD-rewriting ops (reset/checkout/switch)"
swimlane: core
kind: feature
epic: null
labels: [governance, hooks, git-workflow, post-mortem-TASK-012]
status: in_progress
priority: P2
appetite: "1d"
created: 2026-05-22
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-013: Extend branch-guard to block HEAD-rewriting ops (reset/checkout/switch)

**Outcome (one sentence):** branch-guard.sh also BLOCKs git reset to non-HEAD refs, git checkout/switch to non-main branches in trunk mode. Closes the gap TASK-012 left open: branch creation was blocked, but concurrent or accidental HEAD-rewrites still clobbered peer commits. Same hook, expanded scope = one gate = "trunk integrity".

## Read First
- src/core/hooks/branch-guard.sh
- src/core/rules/git-workflow.md
- tests/test_branch_guard.py
- src/core/hooks/block-dangerous-commands.sh

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** an agent in trunk mode (`COS_GIT_WORKFLOW=trunk`, default)
- **When** it runs `git reset HEAD~1`, `git reset <sha>`, `git checkout <other-branch>`, or `git switch <other-branch>`
- **Then** `branch-guard.sh` BLOCKs (exit 2) with a remediation message
  pointing to `git switch main` / `git restore <file>` and the
  `COS_GIT_WORKFLOW=pr` escape hatch.
- **And** the following remain allowed: `git reset` (bare unstage), `git
  reset --mixed HEAD`, `git checkout main`, `git checkout -- <file>`,
  `git checkout HEAD~1 -- <file>` (file restore from sha, HEAD does not
  move), `git switch main`.
- **And** the existing branch-creation blocks (TASK-012) still fire on
  `git checkout -b`, `git branch <name>`, `git switch -c`, `git worktree
  add`.

## Scope Caveats (Rule 22 — explicitly OUT)
- `git rebase`, `git cherry-pick`, `git commit --amend` are NOT blocked
  (rare for vibe-coding consumers; add on incident).
- No new hook file — branch-guard.sh is extended; conceptually one gate
  = "trunk integrity" (create + history-rewrite).
- No new override flag — `COS_GIT_WORKFLOW=pr` seam suffices.

## Work Log

- 2026-05-22 — Extended `branch-guard.sh` with three pure-bash helper
  functions (`_reset_is_head_move`, `_checkout_is_head_move`,
  `_switch_is_branch_move`) so the hook now BLOCKs HEAD-rewriting ops
  alongside branch creation. POSIX-ERE-portable parsing (no `\b`
  dependency). Reason-specific BLOCK messages nudge users toward
  `git restore` / `git switch main` / `git revert`. Added 16 new tests
  (8 block + 8 allow) for a total of 29 in test_branch_guard.py.
  Updated git-workflow.md with the safe-form table + history-rewrite
  anti-patterns. registry description updated. Adapter templates +
  golden parity confirmed green.
- 2026-05-22 — Reviewer subagent (general-purpose) audited commit
  `0edccc3`: PASS-with-followups. Dominant-case gate works (16/16
  block probes, 12/14 false-positive probes correct). 5 hardening
  gaps surfaced (whitespace bypass, `git -C`/`git -c` global options,
  `sh -c` nested, `git checkout .`, literal-string false-positives in
  grep/echo). Filed as [TASK-014](TASK-014-branch-guard-hardening-whitespace-normalize-git-c-c-options-.md)
  (P3, icebox, depends_on TASK-013). Closed TASK-013 as-scoped.
