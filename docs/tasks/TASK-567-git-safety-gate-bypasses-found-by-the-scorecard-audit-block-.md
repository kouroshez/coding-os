---
id: TASK-567
title: "git safety-gate bypasses found by the scorecard audit: block-secrets quote-splice + GIT_CONFIG override, force-push self-override, branch-guard filter-branch/symbolic-ref/commit -a"
swimlane: core
kind: bug
epic: null
labels: [hooks, review-findings, branch-guard, block-secrets, audit-2026-06-24, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-06-25
started: 2026-06-25
completed: 2026-06-25
agent_session: ses-claude-20260624-182639-f22b
depends_on: []
blocked_by: []
references: []
---
# TASK-567: git safety-gate bypasses found by the scorecard audit: block-secrets quote-splice + GIT_CONFIG override, force-push self-override, branch-guard filter-branch/symbolic-ref/commit -a

**Outcome (one sentence):** Close the agent-reachable bypasses of the headline git safety gates that an 8-agent scorecard audit found and I re-verified live — block-secrets quote-splice + GIT_CONFIG override, force-push inline self-override, and branch-guard's missing filter-branch/symbolic-ref/commit-a — fixing them in the shared detectors so both trunk and pr-mode benefit.

## Read First
- src/core/hooks/block-secrets.sh
- src/core/hooks/block-dangerous-commands.sh
- src/core/hooks/_helpers/branch_guard_check.py

## Repro Steps
All 4 re-verified live 2026-06-25 (HEAD ecd58284):
- F1 block-secrets: `git commit --no-ver"i"fy` → rc0, `git commit "--no-verify"` → rc0 (bash `eval set --` collapses the arg to literal `--no-verify` at exec); root cause = COMMAND_NOQUOTES sed strips quoted spans BEFORE scanning.
- F2 block-secrets: `GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.hooksPath GIT_CONFIG_VALUE_0=/dev/null git commit -m x` → rc0 (env-based config override disables hooks, unmatched).
- F3 block-dangerous-commands: inline `COS_ALLOW_FORCE_PUSH_MAIN=1` is honored from the command STRING (its own BLOCK message advertises it) → agent self-bypasses force-push-to-main.
- F4 branch_guard trunk verdict=allow for `git filter-branch --force`, `git symbolic-ref HEAD refs/heads/feat`, `git commit -a -m x` (none in _DISPATCH; the commit case is pr-mode-only).

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the agent Bash hook **When** it sees `git commit --no-ver"i"fy`, `git commit "--no-verify"`, or the `GIT_CONFIG_*=core.hooksPath` env form before `git commit` **Then** block-secrets BLOCKs (rc=2); a clean `git commit -m x` still passes
- **Given** an inline `COS_ALLOW_FORCE_PUSH_MAIN=1 git push --force origin main` **When** the Bash hook runs **Then** block-dangerous-commands still BLOCKs — the override must require a process-env export, not a command-string prefix (mirror the COS_GIT_WORKFLOW seam)
- **Given** trunk mode **When** `git filter-branch --force`, `git symbolic-ref HEAD refs/heads/x`, or `git commit -a -m x` run **Then** branch-guard returns verdict=block
- **Then** every existing branch_guard + TestBlockSecrets + block-dangerous test stays green, new regression tests cover each bypass shape, and `make verify-hooks` passes

## Work Log
- 2026-06-25 [claude]: Plan: extract branch_guard's shlex tokenizer into shared _helpers/git_command_parse.py (Rule-of-Three: branch_guard +…
- 2026-06-25 [claude]: Edit git_command_parse.py
- 2026-06-25 [claude]: Edit check_git_bypass.py
- 2026-06-25 [claude]: Edit block-secrets.sh
- 2026-06-25 [claude]: Edit extract_commit_msg_arg.py
- 2026-06-25 [claude]: Edit git_command_parse.py
- 2026-06-25 [claude]: Edit check_git_bypass.py
- 2026-06-25 [claude]: Edit branch_guard_check.py
- 2026-06-25 [claude]: Edit branch_guard_check.py
- 2026-06-25 [claude]: Edit branch_guard_check.py
- 2026-06-25 [claude]: Edit branch_guard_check.py
- 2026-06-25 [claude]: Edit verify_fixes.py
- 2026-06-25 [claude]: Edit git_command_parse.py
- 2026-06-25 [claude]: Edit git_command_parse.py
- 2026-06-25 [claude]: Edit test_hooks.py
- 2026-06-25 [claude]: Edit test_hooks.py
- 2026-06-25 [claude]: Edit git_command_parse.py
- 2026-06-25 [claude]: Edit branch_guard_check.py
- 2026-06-25 [claude]: Edit branch_guard_check.py
- 2026-06-25 [claude]: Edit branch_guard_check.py
- 2026-06-25 [claude]: Edit block-dangerous-commands.sh
- 2026-06-25 [claude]: Edit block-dangerous-commands.sh
- 2026-06-25 [claude]: Edit verify_f3.py
- 2026-06-25 [claude]: Edit test_hooks.py
- 2026-06-25 [claude]: Edit test_hooks.py
- 2026-06-25 [claude]: Shipped shared _helpers/git_command_parse.py (shlex tokenizer + commit_flags + quote-aware command_groups +…
