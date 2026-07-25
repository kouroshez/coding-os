---
id: TASK-565
title: "harden: fix code-review findings on audit-2026-06-24 hooks (branch_guard read-flag FP + update-ref -m bypass, block-secrets git -c commit -n bypass + hooksPath read FP, cleanup --force footgun)"
swimlane: core
kind: bug
epic: null
labels: [hooks, branch-guard, review-findings, audit-2026-06-24, safety-hook-edit, data-loss, ready]
status: archive
priority: P1
appetite: 1d
created: 2026-06-25
started: 2026-06-24
completed: 2026-06-24
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-565: harden: fix code-review findings on audit-2026-06-24 hooks (branch_guard read-flag FP + update-ref -m bypass, block-secrets git -c commit -n bypass + hooksPath read FP, cleanup --force footgun)

**Outcome (one sentence):** Close every CONFIRMED correctness defect a max-effort review found in TASK-561/562/563: (A) block-secrets fast-path keys on contiguous `git commit` so `git -c x commit -n` / `git  commit` (double-space/tab) bypass the no-verify block — broaden to `*git*commit*`; (B/D) `git update-ref -m <reason> …` shifts positionals so `-m wip refs/heads/main` bypasses and `-m HEAD refs/heads/feature` false-blocks — strip the -m value; (C) `git branch --contains/--merged/--points-at/--no-merged main` are read-only list ops wrongly blocked by `_pr_branch_blocks` non-destructive arm — add a read/list-flag guard; (E) `git branch -c main backup` (copy FROM main) wrongly blocked — copy checks only the target; (K) `git log --grep core.hooksPath` false-blocked — require an assignment/config-write; (G) cleanup `--force` remediation text routes the user into data-loss — reword. Fix in the shared `_pr_branch_blocks`/`_pr_update_ref_blocks` so pr-mode benefits too; pr-mode tests stay green.

## Read First
- src/core/hooks/_helpers/branch_guard_check.py
- src/core/hooks/block-secrets.sh
- src/cli/pr_commands.py
- tests/test_branch_guard.py

## Repro Steps
All 6 confirmed via live smoke 2026-06-25: `git -c foo=bar commit -n`→rc0(allow,should block); `git  commit -n`→rc0; `git update-ref -m wip refs/heads/main HEAD~1`→allow(should block); `git update-ref -m HEAD refs/heads/feature`→block(should allow); `git branch --contains main`/`--merged main`/`--points-at main`/`-c main backup`→block(should allow); `git log --grep core.hooksPath`→rc2(should allow). Root causes: block-secrets.sh fast-path case keys on literal `git commit`; _pr_update_ref_blocks/_check_update_ref take positionals[0] without skipping `-m`'s value; _pr_branch_blocks non-destructive arm treats any first positional as a written ref (ignores read/list flags) and destructive arm checks all positionals incl. copy source; block-secrets hooksPath grep matches any mention.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** COS_GIT_WORKFLOW=trunk **When** `git branch --contains main` / `--merged main` / `--points-at main` / `-c main backup` run **Then** branch_guard returns allow (read/copy-source), while `branch -f/-M/-D main` still block
- **Given** trunk **When** `git update-ref -m wip refs/heads/main HEAD~1` runs **Then** it blocks; **When** `git update-ref -m HEAD refs/heads/feature abc` runs **Then** it allows
- **Given** the agent Bash hook **When** `git -c foo=bar commit -n` / `git  commit -n` (double space) run **Then** block-secrets BLOCKs; **When** `git log --grep core.hooksPath` runs **Then** it passes
- **Then** every existing pr-mode + trunk + TestBlockSecrets test stays green, new regression tests cover each shape, `make verify-hooks` passes, and the cleanup --force remediation warns it discards unpreserved work

## Work Log
- 2026-06-25 [claude]: Edit branch_guard_check.py
- 2026-06-25 [claude]: Edit branch_guard_check.py
- 2026-06-25 [claude]: Edit branch_guard_check.py
- 2026-06-25 [claude]: Edit block-secrets.sh
- 2026-06-25 [claude]: Edit block-secrets.sh
- 2026-06-25 [claude]: Edit block-secrets.sh
- 2026-06-25 [claude]: Edit block-secrets.sh
- 2026-06-25 [claude]: Edit pr_commands.py
- 2026-06-25 [claude]: Edit pr_commands.py
- 2026-06-25 [claude]: Edit pr_commands.py
- 2026-06-25 [claude]: Edit test_hooks.py
- 2026-06-25 [claude]: Edit test_hooks.py
- 2026-06-25 [claude]: Edit test_branch_guard.py
- 2026-06-25 [claude]: Edit test_cli.py
- 2026-06-25 [claude]: Fixed all 6 confirmed review correctness bugs in the SHARED helpers so pr-mode benefits too: branch-guard now ignores…
