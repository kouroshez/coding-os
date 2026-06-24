---
id: TASK-543
title: "branch-guard worktree-spoof + fetch-refspec protected-ref leak"
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
# TASK-543: branch-guard worktree-spoof + fetch-refspec protected-ref leak

**Outcome (one sentence):** branch-guard treats a '..'-traversal worktree-spoof path as shared (block holds) and blocks 'git fetch origin x:main/:production' that writes a protected local ref.

## Read First
- src/core/hooks/_helpers/branch_guard_check.py
- src/core/hooks/block-shared-tree-edit.sh
- tests/test_branch_guard.py
- docs/playbooks/pr-workflow.md

## Repro Steps
1. COS_GIT_WORKFLOW=pr; run branch-guard with `cd /repo/.coding-os/worktrees/x/../../../realmain && git reset HEAD~1`.
2. Run branch-guard with `git fetch origin x:main` (writes local main).
Expected: both BLOCK (spoof resolves into shared checkout; fetch writes protected ref).
Actual: spoof path allowed via raw-string OR-arm; fetch has no arm so it passes.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** COS_GIT_WORKFLOW=pr and a path like .../worktrees/x/../../../realmain that realpath-resolves into the shared checkout
- **When** branch-guard evaluates a commit/HEAD-rewrite scoped to that path, or a `git fetch origin x:main` writing a blocked local ref
- **Then** the op is BLOCKED (spoof path classified shared via realpath only; fetch colon-refspec to a blocked branch returns pr-protected-ref), while legit colon-free fetches and real worktree ops still pass

## Work Log
- 2026-06-24 [claude]: Edit branch_guard_check.py
- 2026-06-24 [claude]: Edit branch_guard_check.py
- 2026-06-24 [claude]: Edit block-shared-tree-edit.sh
- 2026-06-24 [claude]: Edit test_branch_guard.py
- 2026-06-24 [claude]: Edit test_block_shared_tree_edit.py
- 2026-06-24 [claude]: Edit test_block_shared_tree_edit.py
- 2026-06-24 [claude]: Verified: 6 new TASK-543 tests green (spoof/fetch-refspec/colon-free/trunk), full test_branch_guard.py 118 passed,…
- 2026-06-24 [claude]: committed 284e35a0 · 4 files
- 2026-06-24 [claude]: Status transitioned to complete via cos task-done.
