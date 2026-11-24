---
id: TASK-1105
title: "feat(board): every testing round is reviewed, and rework is exempt from the WIP cap"
swimlane: "board_os"
kind: feature
epic: null
labels: [hooks, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-11-24
started: 2026-11-24
completed: 2026-11-24
agent_session: ses-claude-20261123-135444-89e7
depends_on: []
blocked_by: []
references: []
---
# TASK-1105: feat(board): every testing round is reviewed, and rework is exempt from the WIP cap

**Outcome (one sentence):** A review runs for every testing round whether supervision is on or off (supervision only picks the reviewer), a close without a recorded review is announced with a ⚠️ line, and moving a task back from testing for rework is never blocked by the in_progress WIP cap.

## Read First
- docs/engineering/agent-supervision.md
- docs/governance/task-lifecycle.md
- src/core/hooks/_helpers/auto_dispatch.py
- src/core/board_os/review_gate.py
- src/core/board_os/workflow.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** supervision is off, **When** a task moves to testing, **Then** a reviewer runs on the session's own adapter and its result enters the review ledger for that round.
- **Given** supervision is on with reviewer pinned to another provider, **When** a task moves to testing, **Then** that pin reviews and no same-adapter reviewer is added.
- **Given** no review result was recorded for the current round, **When** the task is completed, **Then** completion is allowed with a DOD_REVIEW_SKIPPED warning carrying a ⚠️ BOARD_EVENTS line.
- **Given** the session already has a task in_progress at the cap, **When** another of its tasks moves from testing back to in_progress, **Then** the move succeeds; a pull from icebox stays blocked.

## Work Log
- 2026-11-24 [claude]: Deliberation: the operator's rule is that supervision must not change whether work is reviewed, only who reviews. So…
- 2026-11-24 [claude]: Status transitioned to complete via cos task-done.
