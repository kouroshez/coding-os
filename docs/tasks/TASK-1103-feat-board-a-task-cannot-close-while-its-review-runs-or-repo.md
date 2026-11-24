---
id: TASK-1103
title: "feat(board): a task cannot close while its review runs or reports findings"
swimlane: "board_os"
kind: feature
epic: null
labels: [hooks, governance, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-11-24
started: 2026-11-23
completed: 2026-11-23
agent_session: ses-claude-20261123-135444-89e7
depends_on: []
blocked_by: []
references: []
---
# TASK-1103: feat(board): a task cannot close while its review runs or reports findings

**Outcome (one sentence):** The review loop closes itself: completion waits for the cross-provider review of the current testing round, findings send the task back to in_progress and a fresh round runs on the next testing move, and the user sees each step as a line the agent echoes.

## Read First
- docs/engineering/agent-supervision.md
- src/core/board_os/transition_gates_validator.py
- src/core/board_os/_workflow_gates.py
- src/core/hooks/_helpers/auto_dispatch.py
- src/core/hooks/auto-dispatch-crossprovider.sh
- src/core/rules/transparency-banner.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a task whose current testing round has a review still running, **When** it is moved to complete by any path, **Then** the board refuses with DOD_REVIEW_PENDING and a BOARD_EVENTS line starting with ⏳.
- **Given** the current round's review reported findings, **When** the task is moved to complete, **Then** the board refuses with DOD_REVIEW_FINDINGS and a BOARD_EVENTS line starting with 🔍 that names the first finding.
- **Given** the task went back to in_progress and then to testing again, **When** that move lands, **Then** a new review round is dispatched and only that round decides the gate.
- **Given** supervision is off, the review row is older than its stale cap, or COS_VERIFY_OVERRIDE with a reason is set, **When** the task is completed, **Then** the gate does not block.

## Work Log
- 2026-11-24 [claude]: Deliberation: the gate lives in the board's Definition of Done (evaluate_dod), not a hook, because every completion…
- 2026-11-24 [claude]: Live drill on the real board via cos task-done (supervision was turned off in the Hub, so ledger rows for round 1…
- 2026-11-24 [claude]: Status transitioned to complete via cos task-done.
