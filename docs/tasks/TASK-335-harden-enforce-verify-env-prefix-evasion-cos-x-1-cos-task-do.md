---
id: TASK-335
title: "Harden enforce-verify: env-prefix evasion (COS_X=1 cos task-done skips the gate) + record-verify-auto failure-path lock release"
swimlane: core
kind: bug
epic: null
labels: [test-governance, hooks, hardening, ready]
status: icebox
priority: P1
appetite: 1d
created: 2026-06-10
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-335: Harden enforce-verify: env-prefix evasion (COS_X=1 cos task-done skips the gate) + record-verify-auto failure-path lock release

**Outcome (one sentence):** enforce-verify strips leading env assignments before segment matching (same _command_segments discipline as test-governor); record-verify-auto also registered for PostToolUseFailure (or equivalent) so a failed suite clears .test-run.lock immediately instead of waiting for the 120s grace+liveness expiry.

## Read First
- src/core/hooks/enforce-verify.sh
- src/core/board_os/verify_suites_cli.py
- docs/engineering/test-governance.md
- src/core/hooks/registry.yaml

## Repro Steps
1. (fill in: exact steps to reproduce)
2. ...
Expected: ...
Actual: ...

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** COS_VERIFY_OVERRIDE=1 cos task-done TASK-N as one command
- **When** enforce-verify fires
- **Then** the gate evaluates (override path honored, not skipped); and a FAIL-exiting suite command clears the run lock in the same turn

## Work Log
