---
id: TASK-1140
title: "fix(hooks): a background suite launch frees the test-run lock again"
swimlane: infra
kind: bug
epic: null
labels: [ready]
status: complete
priority: P1
appetite: 1h
created: 2026-11-26
started: 2026-11-26
completed: 2026-11-26
agent_session: ses-claude-20261126-141006-6f9e
depends_on: []
blocked_by: []
references: []
---
# TASK-1140: fix(hooks): a background suite launch frees the test-run lock again

**Outcome (one sentence):** A suite started with run_in_background never leaves the shared test-run lock held after it ends; the ledger still records nothing for the launch (TASK-1132).

## Read First
- src/core/hooks/record-verify-auto.sh
- docs/engineering/test-governance.md

## Repro Steps
TASK-1132 made a background launch keep the lock; PostToolUse fires only at launch, so nothing clears it at completion and, the owner being a live claude process, every other session is blocked until the 1800s TTL (seen 2026-11-26 after a background board_os run).

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a PostToolUse for a background pytest suite launch, **When** record-verify-auto runs, **Then** no ledger entry is written and the test-run lock is cleared.
- **Given** a background launch of a command that only mentions pytest, **When** record-verify-auto runs, **Then** a sibling's lock is kept.

## Work Log
- 2026-11-26 [claude]: e92a2427: record-verify-auto computes MATCH/IS_PYTEST and clears .test-run.lock before the background-launch exit, so…
- 2026-11-26 [claude]: Status transitioned to complete via cos task-done.
