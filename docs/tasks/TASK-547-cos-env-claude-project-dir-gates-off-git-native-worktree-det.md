---
id: TASK-547
title: "cos-env CLAUDE_PROJECT_DIR gates off git-native worktree detection (state misroute)"
swimlane: core
kind: bug
epic: pr-mode-hardening
labels: [ready]
status: complete
priority: P1
appetite: 1d
created: 2026-06-24
started: 2026-06-24
completed: 2026-06-24
agent_session: ses-claude-20260624-034200-e9e7
depends_on: []
blocked_by: []
references: []
---
# TASK-547: cos-env CLAUDE_PROJECT_DIR gates off git-native worktree detection (state misroute)

**Outcome (one sentence):** cos-env.sh runs the git-native worktree-detection fallback even when CLAUDE_PROJECT_DIR is set (gate only on COS_PROJECT_ROOT), so a custom-location worktree no longer misroutes state into the worktree.

## Read First
- src/core/hooks/cos-env.sh
- docs/playbooks/pr-workflow.md

## Repro Steps
1. pr-mode worktree at a custom path (COS_WORKTREE_ROOT outside the raw /.coding-os/worktrees/ string); CLAUDE_PROJECT_DIR set (Claude Code), COS_PROJECT_ROOT unset.
2. A hook sources cos-env.sh from that worktree cwd.
Expected: git-native probe runs, _cos_in_wt=1, state binds to MAIN repo.
Actual: line-152 guard short-circuits on CLAUDE_PROJECT_DIR → probe skipped → state misroutes into the worktree (stray .coding-os committed into the PR).

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** Claude Code runs (CLAUDE_PROJECT_DIR set) inside a custom-location worktree outside the raw /.coding-os/worktrees/ string, with COS_PROJECT_ROOT unset
- **When** a hook sources cos-env.sh and the cheap toplevel != git-common-dir-parent probe detects a worktree
- **Then** state binds to the MAIN repo (no stray .coding-os committed into the agents PR); a normal non-worktree hook in trunk mode never forks git (fast path preserved)

## Work Log
- 2026-06-24 [claude]: Edit cos-env.sh
- 2026-06-24 [claude]: Edit cos-env.sh
- 2026-06-24 [claude]: commit dbfa08632c — fix(pr-mode): submit fails safe on gh-down + honest local rung + heal-budget flock + pid-unique tmp
- 2026-06-24 [claude]: Edit fixd_test.sh
- 2026-06-24 [claude]: committed 421480f5 · 1 file
- 2026-06-24 [claude]: Status transitioned to complete via cos task-done.
