---
id: TASK-1132
title: "Verify ledger must not record a background suite launch as PASS"
swimlane: infra
kind: bug
epic: null
labels: [ready]
status: in_progress
priority: P1
appetite: 2h
created: 2026-11-26
started: 2026-11-26
completed: null
agent_session: ses-claude-20261125-165238-7b8d
depends_on: []
blocked_by: []
references: []
---
# TASK-1132: Verify ledger must not record a background suite launch as PASS

**Outcome (one sentence):** A suite started with run_in_background never reaches .last-verify.json as PASS and does not free the test-run lock it still holds.

## Read First
- src/core/hooks/record-verify-auto.sh
- tests/test_test_governor.py
- docs/engineering/test-governance.md

## Repro Steps
Run a matrix suite with run_in_background: Claude Code fires PostToolUse at launch with tool_response {stdout:"", backgroundTaskId:...} and no exit_code; the hook treats that as success and writes PASS before the suite has run, so cos task-done accepts a suite that may fail.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a PostToolUse for a verify-suite command with tool_input.run_in_background true or a tool_response.backgroundTaskId, **When** record-verify-auto runs, **Then** no ledger entry is written and the test-run lock is kept.
- **Given** the same suite run in the foreground, **When** it succeeds, **Then** it is still recorded PASS and the lock is cleared.

## Work Log
