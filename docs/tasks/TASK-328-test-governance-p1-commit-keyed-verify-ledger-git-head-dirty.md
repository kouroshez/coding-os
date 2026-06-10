---
id: TASK-328
title: "Test-governance P1: commit-keyed verify ledger \u2014 git_head/dirty_digest/agent in .last-verify.json, freshness = tree match + TTL"
swimlane: "board_os"
kind: feature
epic: test-governance
labels: [test-governance, ledger, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-06-10
started: 2026-06-09
completed: 2026-06-09
agent_session: ses-claude-20260527-151803-0b9f
depends_on: [TASK-327]
blocked_by: []
references: []
---
# TASK-328: Test-governance P1: commit-keyed verify ledger — git_head/dirty_digest/agent in .last-verify.json, freshness = tree match + TTL

**Outcome (one sentence):** verify_suites_cli check treats a PASS as fresh ONLY when git_head+dirty_digest match the current tree AND age<=max_age; record-verify.sh writes the new fields; entries missing the keys = stale (backward compatible).

## Read First
- docs/engineering/test-governance.md
- src/core/board_os/verify_suites.py
- src/core/board_os/verify_suites_cli.py
- src/core/hooks/record-verify.sh
- src/core/hooks/enforce-verify.sh

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a PASS recorded on tree T
- **When** a new commit lands or the dirty diff changes
- **Then** check reports the suite stale; unchanged tree within TTL stays fresh; legacy entries without keys are stale; board_os matrix suite green

## Work Log
- 2026-06-10 [claude]: Status transitioned to complete via cos task-done.
