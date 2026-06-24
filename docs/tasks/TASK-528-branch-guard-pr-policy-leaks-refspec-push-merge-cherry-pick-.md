---
id: TASK-528
title: "branch-guard pr-policy leaks \u2014 refspec push, merge/cherry-pick, branch -f/update-ref mutate protected branches"
swimlane: core
kind: security
epic: pr-mode-hardening
labels: [pr-mode, branch-guard, critical, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-06-23
started: 2026-06-23
completed: 2026-06-23
agent_session: ses-claude-20260623-175054-847a
depends_on: []
blocked_by: []
references: []
---
# TASK-528: branch-guard pr-policy leaks — refspec push, merge/cherry-pick, branch -f/update-ref mutate protected branches

**Outcome (one sentence):** In pr-mode the positive policy fully walls the integration + protected branches against direct mutation outside the PR flow — full-ref refspec pushes are blocked by stripping refs/heads/ before the membership test; git merge/cherry-pick on the SHARED checkout are treated like reset/rebase (allowed only worktree-scoped); git branch -f/-D/-m and git update-ref targeting a blocked branch are blocked unless worktree-scoped; trunk mode stays byte-identical.

## Read First
- src/core/hooks/_helpers/branch_guard_check.py
- src/core/hooks/branch-guard.sh
- docs/playbooks/pr-workflow.md

## Threat Model
An autonomous (or buggy/compromised) agent in a pr-mode consumer must NOT be able to land code on the integration or protected (production) branch outside the PR+CI flow. Today three git invocation shapes bypass the wall: (1) `git push origin HEAD:refs/heads/main` — `_push_targets` strips only the bare name and never `refs/heads/`, so the fully-qualified ref pushes straight through; (2) `git merge` / `git cherry-pick` on the shared integration checkout advance the always-green line and fall through `_pr_check` to allow; (3) `git branch -f <integration>` / `git update-ref refs/heads/<integration>` rewrite the ref directly and fall through to allow. Impact = an agent can corrupt or fast-forward production with no human/CI gate — the exact invariant ('agents have zero permission on production') the spec sells. Blast radius: every consumer that enables pr-mode.

## Repro Steps
COS_GIT_WORKFLOW=pr COS_GIT_INTEGRATION_BRANCH=main COS_GIT_PROTECTED_BRANCHES=production; pipe each command through branch_guard_check.py — `git push origin HEAD:refs/heads/main`, `git merge agents/x/y`, `git branch -f main HEAD~1`, `git update-ref refs/heads/main HEAD~1` all return verdict=allow (must block).

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** pr-mode **When** `git push origin HEAD:refs/heads/main` / `+refs/heads/main` / `refs/heads/production` **Then** BLOCK.
- **Given** the shared checkout **When** `git merge` / `git cherry-pick` **Then** BLOCK; **When** the same inside a worktree **Then** allow.
- **Given** the shared checkout **When** `git branch -f main` / `git update-ref refs/heads/main` **Then** BLOCK.
- **Given** trunk mode **When** any of the above **Then** behavior is unchanged.
- **And** `make verify-hooks` + `uv run pytest tests/test_branch_guard.py -q` are green with new probes.

## Work Log
- 2026-06-24 [claude]: Deliberation: close the 3 branch-guard pr leaks by EXTENDING the positive allow-list (reuse…
- 2026-06-24 [claude]: Edit pr-workflow.md
- 2026-06-24 [claude]: Edit branch_guard_check.py
- 2026-06-24 [claude]: Edit branch_guard_check.py
- 2026-06-24 [claude]: Edit branch_guard_check.py
- 2026-06-24 [claude]: Edit test_branch_guard.py
- 2026-06-24 [claude]: commit 9cc7a1d979 — fix(pr-mode): branch-guard blocks refspec-push/merge/cherry-pick/branch-f/update-ref leaks
- 2026-06-24 [claude]: Status transitioned to complete via cos task-done.
