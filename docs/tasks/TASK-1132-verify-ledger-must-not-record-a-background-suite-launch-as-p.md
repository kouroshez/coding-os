---
id: TASK-1132
title: "Verify ledger must not record a background suite launch as PASS"
swimlane: infra
kind: bug
epic: null
labels: [ready]
status: complete
priority: P1
appetite: 2h
created: 2026-11-26
started: 2026-11-26
completed: 2026-11-26
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
- 2026-11-26 [claude]: commit 07222f7db1 — docs(tasks): TASK-1131 work log
- 2026-11-26 [claude]: record-verify-auto now skips (reason=background-launch) a payload with tool_input.run_in_background or…
- 2026-11-26 [claude]: commit 8eb704fa2e — docs(hooks): plainer wording for the background-launch rule
- 2026-11-26 [claude]: Correction: the fix is 7864d149 (+ wording 8eb704fa); 07222f7d named above is the TASK-1131 work-log commit. Review…
- 2026-11-26 [claude]: Status transitioned to complete via cos task-done.
