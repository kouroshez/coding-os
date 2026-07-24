---
id: TASK-536
title: "branch-guard pr-policy still leaks to protected \u2014 heads/ refspec, bare push from shared, push.default=matching, worktree/checkout -B onto protected"
swimlane: core
kind: security
epic: pr-mode-p0-hardening
labels: [pr-mode, branch-guard, critical, ready]
status: archive
priority: P0
appetite: 1d
created: 2026-06-24
started: 2026-06-24
completed: 2026-06-24
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-536: branch-guard pr-policy still leaks to protected — heads/ refspec, bare push from shared, push.default=matching, worktree/checkout -B onto protected

**Outcome (one sentence):** No git form lets an agent write/push a protected or integration branch in pr-mode: heads/ refspec shorthand is normalized, bare/HEAD push is only allowed worktree-scoped (or with an explicit agents/* refspec), -c push.default=matching is refused, and checkout -B / switch -C / worktree add onto a blocked branch is blocked. Worktree pushes stay safe because a worktree can no longer be created on a blocked branch.

## Read First
- src/core/hooks/_helpers/branch_guard_check.py
- tests/test_branch_guard.py
- docs/playbooks/pr-workflow.md

## Threat Model
A consumer runs 5+ autonomous agents in pr-mode. The branch-guard is the wall that keeps an agent off the protected (live/production) and integration branches — agents may only touch their own agents/* branch and land via PR+CI. Confirmed bypasses that defeat the wall: (1) `git push origin HEAD:heads/production` — `_unqualify_ref` strips only `refs/heads/`, so the `heads/` shorthand maps to `heads/production` not in the blocked set → direct push to production; (2) a bare/HEAD `git push` from the shared checkout (which sits on integration) advances integration outside PR+CI; (3) `git -c push.default=matching push` is a git global stripped before `_pr_check` sees it → pushes every same-name branch incl. main; (4) `git checkout -B main` / `git switch -C main` / `git worktree add <wt> main` force-create/checkout the protected ref (the last also lets a worktree sit on main, defeating the worktree-scoped push assumption). Attacker = a confused or prompt-injected agent; impact = corrupting the always-green integration line or pushing to the human-only production line.

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** pr-mode enabled with protected={production} integration={main}, **When** an agent runs `git push origin HEAD:heads/production`, a bare/HEAD `git push` from the shared checkout, `git -c push.default=matching push`, `git checkout -B main`, or `git worktree add <wt> main`, **Then** branch-guard BLOCKs each (exit 2). **And** the sanctioned flow still passes: agents/* branch create, `git worktree add <wt> origin/main`, and a worktree-scoped `git push --force-with-lease -u origin HEAD`. Verified by `uv run pytest tests/test_branch_guard.py -q` + `make verify-hooks`.

## Work Log
- 2026-06-24 [claude]: Edit pr-workflow.md
- 2026-06-24 [claude]: Edit branch_guard_check.py
- 2026-06-24 [claude]: Edit branch_guard_check.py
- 2026-06-24 [claude]: Edit branch_guard_check.py
- 2026-06-24 [claude]: Edit branch_guard_check.py
- 2026-06-24 [claude]: Edit branch_guard_check.py
- 2026-06-24 [claude]: Edit test_branch_guard.py
- 2026-06-24 [claude]: Chose to make 'a worktree's HEAD is always a non-blocked branch' a hard invariant (block…
- 2026-06-24 [claude]: committed c4f50569 · 3 files
