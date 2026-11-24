---
id: TASK-1107
title: "fix(review): a malformed verify ledger timestamp never stops the review from starting"
swimlane: "board_os"
kind: bug
epic: null
labels: [hooks, ready]
status: complete
priority: P2
appetite: 1d
created: 2026-11-24
started: 2026-11-24
completed: 2026-11-24
agent_session: ses-claude-20261123-135444-89e7
depends_on: []
blocked_by: []
references: []
---
# TASK-1107: fix(review): a malformed verify ledger timestamp never stops the review from starting

**Outcome (one sentence):** review_context skips a verify-ledger entry whose ts is not a number instead of raising, so the review still dispatches.

## Read First
- src/core/hooks/_helpers/auto_dispatch.py
- tests/test_auto_dispatch_crossprovider.py

## Repro Steps
TASK-1106 review round 3 note 5: review_context calls int(run.get('ts') or 0) outside the try that guards the file read; a non-numeric ts raises ValueError in the detached helper, so no review row is ever written.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** .last-verify.json holds an entry with ts "yesterday", **When** a task moves to testing, **Then** the review still dispatches and verification_evidence lists only the well-formed entries.

## Work Log
- 2026-11-24 [claude]: Status transitioned to complete via cos task-done.
- 2026-11-24 [claude]: review_context now keeps only numeric ts entries, so a hand-edited .last-verify.json cannot crash the detached review…
