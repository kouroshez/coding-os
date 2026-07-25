---
id: TASK-563
title: "Harden the --no-verify block (block-secrets.sh): -n short flag, leading path/cd/env prefix, and -c core.hooksPath all bypass the anchored regex"
swimlane: core
kind: bug
epic: null
labels: [hooks, commit-contract, audit-2026-06-24, safety-hook-edit, ready]
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
# TASK-563: Harden the --no-verify block (block-secrets.sh): -n short flag, leading path/cd/env prefix, and -c core.hooksPath all bypass the anchored regex

**Outcome (one sentence):** block-secrets.sh blocks every agent form that skips git hooks at commit — `git commit -n`, a leading path / `cd … &&` / env-assignment prefix before `git`, and `git -c core.hooksPath=… commit` — not just the exact `^git commit … --no-verify`. The git-workflow.md "no escape hatch for agents" promise becomes true for the agent Bash path; the git-level commit-msg/pre-commit hooks remain the human backstop.

## Read First
- src/core/hooks/block-secrets.sh
- src/core/rules/git-workflow.md
- src/core/hooks/_helpers/check_commit_message.py

## Repro Steps
Audit GH-1 (CONFIRMED via scratchpad/nv.sh): block-secrets.sh:51 uses `grep -qE '^git commit\b.*--no-verify'`. Only the exact form blocks; `git commit -n`, `/usr/bin/git commit --no-verify`, `cd foo && git commit --no-verify`, `env … git commit --no-verify`, and `git -c core.hooksPath=/dev/null commit` all PASS the hook while skipping the git-level pre-commit/commit-msg chain. The non-anchored enforce-commit-message.sh:27 still validates the message for the -n/prefixed forms, so message-format partially survives.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the agent PreToolUse Bash hook **When** it sees `git commit -n -m x`, `/usr/bin/git commit --no-verify`, `cd d && git commit --no-verify`, or `git -c core.hooksPath=/dev/null commit` **Then** block-secrets.sh BLOCKs (exit 2)
- **Given** a normal `git commit -m x` **When** the hook runs **Then** it passes (no false positive)
- **Then** `make verify-hooks` passes and a regression test covers each bypass shape

## Work Log
- 2026-06-25 [claude]: Edit block-secrets.sh
- 2026-06-25 [claude]: Edit smoke_noverify.py
- 2026-06-25 [claude]: Edit block-secrets.sh
- 2026-06-25 [claude]: Edit test_hooks.py
- 2026-06-25 [claude]: Edit git-workflow.md
- 2026-06-25 [claude]: Replaced the anchored ^git commit…--no-verify grep with per-shell-segment detection (split on ;&|) so leading path /…
