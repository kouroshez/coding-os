---
id: TASK-566
title: "pr-cleanup + session-end edge findings deferred from TASK-565 review (post-merge unpushed preserve, subdir-cwd advisory, non-md docs)"
swimlane: core
kind: bug
epic: null
labels: [pr-mode, hooks, review-findings, edge-case, audit-2026-06-24, ready]
status: complete
priority: P3
appetite: 1d
created: 2026-06-25
started: 2026-06-25
completed: 2026-06-25
agent_session: ses-claude-20260624-182639-f22b
depends_on: []
blocked_by: []
references: []
---
# TASK-566: pr-cleanup + session-end edge findings deferred from TASK-565 review (post-merge unpushed preserve, subdir-cwd advisory, non-md docs)

**Outcome (one sentence):** Close the three lower-severity edges the TASK-565 max-effort review surfaced but deliberately deferred: (H) cos pr cleanup preserves only on a DIRTY tree, diverging from _reap_one's (not recoverable or dirty) — a drifted peer whose PR is merged/closed but has clean-tree UNPUSHED local commits skips both the merge-gate (state not in none/unknown) and the dirty-preserve block, so branch -D discards them with no bundle; (J) session-end.sh's advisory uses cwd-relative `git status -- . :(exclude)docs` / `-- docs`, so a Stop firing from a repo SUBDIR misses changes elsewhere — anchor to the repo top-level; (N) an uncommitted NON-.md docs file (png/json) is counted by neither advisory (docs grep is .md-only, code advisory excludes docs/).

## Read First
- src/cli/pr_commands.py
- src/core/hooks/session-end.sh
- src/cli/pr_commands.py

## Repro Steps
From TASK-565 max-effort review (adversarial verifiers, 2026-06-25): finding H — pr_commands.py drift-preserve block tests only `_status.stdout.strip()` for dirtiness; for state in {merged,closed} the `_branch_recoverable` gate at ~865 is skipped, so clean-tree unpushed commits fall through to `branch -D` unbundled (reaper's _reap_one preserves on `not recoverable or dirty`). Finding J — session-end.sh `git status --porcelain -- . :(exclude)docs` and `-- docs` are cwd-relative; verified from a subdir both return empty while root shows the change. Finding N — `git status -- docs | grep .md$` plus `:(exclude)docs` leave a non-md docs file uncounted.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a drifted peer worktree with a CLEAN tree but unpushed local commits on a merged/closed branch **When** cos pr cleanup runs **Then** it bundles before branch -D (mirror _reap_one's not-recoverable arm), not silently discards
- **Given** the Stop hook fires from a repo subdirectory with uncommitted code at the root **When** session-end.sh runs **Then** the advisory still reports it (top-level-anchored status)
- **Given** an uncommitted docs/assets/x.png **When** the Stop hook fires **Then** some advisory surfaces it
- **Then** make verify-hooks + the pr/cleanup + hooks suites stay green with regression tests for each

## Work Log
- 2026-06-25 [claude]: Edit session-end.sh
- 2026-06-25 [claude]: Edit pr_commands.py
- 2026-06-25 [claude]: Edit pr_commands.py
- 2026-06-25 [claude]: Edit test_cli.py
- 2026-06-25 [claude]: Edit test_hooks.py
- 2026-06-25 [claude]: Edit test_hooks.py
- 2026-06-25 [claude]: Edit test_hooks.py
- 2026-06-25 [claude]: H: cos pr cleanup now mirrors _reap_one — kept the none/unknown 'submit first' refuse (interactive UX), added a…
