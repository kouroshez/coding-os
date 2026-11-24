---
id: TASK-1106
title: "feat(board): one complete review per round, every finding at once, severity-gated, capped at three rounds"
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
# TASK-1106: feat(board): one complete review per round, every finding at once, severity-gated, capped at three rounds

**Outcome (one sentence):** A review reports every finding in one pass, the agent receives all of them with severities and fixes them in a single rework, only critical/high/medium findings send the task back, and a third failing round stops the loop for the operator instead of bouncing forever.

## Read First
- docs/engineering/agent-supervision.md
- src/core/thinking_os/agents/reviewer.md
- src/core/thinking_os/agents/security_auditor.md
- src/core/board_os/review_gate.py
- src/core/hooks/_helpers/auto_dispatch.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a review that reports seven findings, **When** completion is refused, **Then** the refusal lists all seven, numbered, not the first three.
- **Given** a round whose findings are all low or info, **When** the task is completed, **Then** it closes with a DOD_REVIEW_NOTES warning and a 📝 line instead of going back.
- **Given** the third review round still has a blocking finding, **When** the task is completed, **Then** the board refuses with DOD_REVIEW_ESCALATE and a 🛑 line telling the agent to move it to blocked for the operator.
- **Given** round two of a review, **When** the reviewer is dispatched, **Then** its input carries the round-one findings so it checks those first.

## Work Log
- 2026-11-24 [claude]: Deliberation: board history shows 905 tasks entered testing and only 17 ever went back, while review output was…
- 2026-11-24 [claude]: Status transitioned to complete via cos task-done.
- 2026-11-24 [claude]: Live loop on this very task with the real reviewer@claude (supervision off): round 1 found 8 (4 blocking) — every one…
