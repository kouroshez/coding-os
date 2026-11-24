---
id: TASK-1122
title: "fix(review): no review prompt when the move to testing was refused"
swimlane: "board_os"
kind: bug
epic: null
labels: [supervision, hooks, ready]
status: complete
priority: P1
appetite: 2h
created: 2026-11-24
started: 2026-11-24
completed: 2026-11-24
agent_session: ses-claude-20261124-140244-e2ad
depends_on: []
blocked_by: []
references: []
---
# TASK-1122: fix(review): no review prompt when the move to testing was refused

**Outcome (one sentence):** The PostToolUse review hook plans a review only when the task really entered testing, so a move refused by a DB lock or the testing WIP cap asks for no subagent and writes no running row.

## Read First
- docs/engineering/agent-supervision.md
- src/core/hooks/_helpers/native_review.py
- src/core/hooks/_helpers/auto_dispatch.py

## Repro Steps
Fill the testing WIP cap (or hold the board DB lock).
Run cos task-move TASK-N --to testing; the move is refused.
The PostToolUse hook still answers 'Start the review of TASK-N round 0 now' and writes running rows for round 0 (seen twice by a sibling session on 2026-11-24).

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a move to testing that the board refused, **When** the PostToolUse review hook runs, **Then** it prints no review instruction, writes no ledger row or request, and starts no detached review.
**Given** a task whose status really is testing after the move, **When** the hook runs, **Then** it plans the round as before.

## Work Log
- 2026-11-24 [claude]: commit 37a02bfcbb — fix(review): a refused move to testing plans no review
- 2026-11-24 [claude]: commit 4f86c46025 — fix(review): an unreadable task status still plans the review
- 2026-11-24 [claude]: Status transitioned to complete via cos task-done.
