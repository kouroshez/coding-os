---
id: TASK-562
title: "branch-guard trunk mode: block force-rewrite of the integration ref (branch -f/-M/-c, update-ref) \u2014 parity with pr-mode"
swimlane: core
kind: bug
epic: null
labels: [branch-guard, hooks, audit-2026-06-24, safety-hook-edit, ready]
status: archive
priority: P2
appetite: 1d
created: 2026-06-24
started: 2026-06-24
completed: 2026-06-24
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-562: branch-guard trunk mode: block force-rewrite of the integration ref (branch -f/-M/-c, update-ref) — parity with pr-mode

**Outcome (one sentence):** In trunk mode, branch_guard_check.py blocks the create-or-force-write forms of `git branch` (-f/-M/-C/-c targeting the integration/main ref) and gains an `update-ref` checker blocking writes/deletes of refs/heads/<integration> and HEAD, reusing the pr-mode _pr_branch_blocks / _pr_update_ref_blocks logic — closing the inversion where pr-mode is STRICTLY stronger than trunk on ref rewrite. merge/cherry-pick stay ALLOWED in trunk (intentional, byte-identical-trunk contract: test_trunk_merge_unchanged / TASK-528). git-workflow.md updated to list the newly-blocked forms.

## Read First
- src/core/hooks/_helpers/branch_guard_check.py
- src/core/rules/git-workflow.md
- tests/test_branch_guard.py

## Repro Steps
Audit BG-1/BG-2 (CONFIRMED via probe): COS_GIT_WORKFLOW=trunk `git branch -f main deadbeef` → allow while pr-mode blocks the identical command; `git update-ref refs/heads/main deadbeef` → allow. _check_branch (branch_guard_check.py:153-159) returns (None,None) on any arg starting with '-'; _DISPATCH (218-225) has no 'update-ref' key so _evaluate_trunk falls through to allow. Both are blocked in pr-mode via _pr_branch_blocks (507-521) / _pr_update_ref_blocks (524-528).

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** COS_GIT_WORKFLOW=trunk **When** an agent runs `git branch -f main <sha>` / `git branch -M main` / `git update-ref refs/heads/main <sha>` **Then** branch_guard_check.py returns verdict=block (parity with pr-mode)
- **When** the same trunk mode sees `git merge` / `git cherry-pick` **Then** it still returns allow and test_trunk_merge_unchanged stays green
- **Then** new trunk regression tests mirror the pr cases and `make verify-hooks` passes

## Work Log
- 2026-06-25 [claude]: Edit branch_guard_check.py
- 2026-06-25 [claude]: Edit branch_guard_check.py
- 2026-06-25 [claude]: Edit branch_guard_check.py
- 2026-06-25 [claude]: Edit branch_guard_check.py
- 2026-06-25 [claude]: Edit test_branch_guard.py
- 2026-06-25 [claude]: Edit git-workflow.md
- 2026-06-25 [claude]: Edit git-workflow.md
- 2026-06-25 [claude]: Reused pr-mode's tested _pr_branch_blocks/_pr_update_ref_blocks for trunk instead of writing new ref-parsing logic…
