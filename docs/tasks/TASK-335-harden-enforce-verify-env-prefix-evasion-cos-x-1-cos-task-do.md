---
id: TASK-335
title: "Harden enforce-verify: env-prefix evasion (COS_X=1 cos task-done skips the gate) + record-verify-auto failure-path lock release"
swimlane: core
kind: bug
epic: null
labels: [test-governance, hooks, hardening, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-06-10
started: 2026-06-10
completed: 2026-06-10
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-335: Harden enforce-verify: env-prefix evasion (COS_X=1 cos task-done skips the gate) + record-verify-auto failure-path lock release

## Outcome
enforce-verify strips leading env assignments before segment matching (same _command_segments discipline as test-governor); record-verify-auto also registered for PostToolUseFailure (or equivalent) so a failed suite clears .test-run.lock immediately instead of waiting for the 120s grace+liveness expiry.

## Read First
- src/core/hooks/enforce-verify.sh
- src/core/board_os/verify_suites_cli.py
- docs/engineering/test-governance.md
- src/core/hooks/registry.yaml

## Repro Steps
1. Run as ONE Bash command: `COS_VERIFY_OVERRIDE=1 cos task-done TASK-NNN` with dirty matrix-matched files and a stale ledger.
2. Pre-fix: the segment matcher only recognized segments STARTING with "cos task-done" — the env prefix made the gate skip silently (exit 0, no evaluation).
3. Separately: kill a suite command mid-run — PostToolUse never fires, `.test-run.lock` lingers for the 120s grace window and self-blocks the same panel.
Expected: gate fires and evaluates the audited override; failed/killed runs record FAIL and free the lock immediately.
Actual (pre-fix): gate silently skipped; lock held until grace+liveness expiry.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** COS_VERIFY_OVERRIDE=1 cos task-done TASK-N as one command
- **When** enforce-verify fires
- **Then** the gate evaluates (override path honored, not skipped); and a FAIL-exiting suite command clears the run lock in the same turn

## Work Log
- 2026-06-10 fixed: env-prefix strip + inline override export in enforce-verify.sh; PostToolUseFailure event on record-verify-auto (forces FAIL, frees lock); governor reclaims own-session lock. verify-hooks green, governor suite 23 pass, both smoke directions verified. Commit on main.
- 2026-06-10 [claude]: Status transitioned to complete via cos task-done.
