---
id: TASK-203
title: "pre-commit deadlocks on large staged set \u2014 here-string self-pipe write blocks (bash 5.x heredoc)"
swimlane: core
kind: bug
epic: null
labels: [git, hooks, deadlock, ready]
status: archive
priority: P1
appetite: 1d
created: 2026-06-06
started: 2026-06-05
completed: 2026-06-05
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-203: pre-commit deadlocks on large staged set — here-string self-pipe write blocks (bash 5.x heredoc)

**Outcome (one sentence):** .git/hooks/pre-commit no longer deadlocks when the staged set is large: the FILE_ARGS array is built via process substitution (drained line-by-line) instead of a `done <<< "$STAGED_FILES"` here-string whose self-pipe write blocks once the list exceeds the pipe buffer. Guarded by tests/test_pre_commit_no_deadlock.py.

## Read First
- src/scripts/_pre_commit_body.sh
- src/core/rules/git-workflow.md

## Repro Steps
1. Stage a large set of files (>5000 paths, ~300KB) so the staged list exceeds the OS pipe buffer (~64KB).
2. Run `git commit` — .git/hooks/pre-commit drains the list with `done <<< "$STAGED_FILES"`.
Expected: commit completes.
Actual (pre-fix): the here-string self-pipe write blocks once the list exceeds the pipe buffer → pre-commit deadlocks → commit hangs.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** .git/hooks/pre-commit (src/scripts/_pre_commit_body.sh) drains the staged-file list into the FILE_ARGS array
- **When** the staged set is large enough to exceed the OS pipe buffer (>5000 paths)
- **Then** FILE_ARGS is built via process substitution `done < <(printf '%s\n' "$STAGED_FILES")` with zero `done <<<` here-strings remaining in src/**/*.sh, the commit completes without deadlock, and tests/test_pre_commit_no_deadlock.py passes (3/3)

## Work Log
- 2026-06-06 [claude]: committed 2e8b26b1: src/scripts/_pre_commit_body.sh, tests/test_pre_commit_no_deadlock.py
- 2026-06-06 [claude]: Fixed: pre-commit + 3 hooks converted done <<< $VAR -> done < <(printf). Commits 2e8b26b1, 5a892f87. Repo-wide guard tes
- 2026-06-06 [claude]: Status transitioned to complete via cos task-done.
