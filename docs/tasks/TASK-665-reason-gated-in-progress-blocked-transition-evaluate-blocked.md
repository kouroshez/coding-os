---
id: TASK-665
title: "Reason-gated in_progress\u2192blocked transition (evaluate_blocked, warn-first) + blocker taxonomy"
swimlane: "board_os"
kind: feature
epic: blocked-lane-management
labels: [blocked, gates, taxonomy, ready]
status: blocked
priority: P2
appetite: 1d
created: 2026-06-30
started: null
completed: null
agent_session: ses-claude-20260628-125542-fc9a
depends_on: [TASK-663]
blocked_by: []
references: []
---
# TASK-665: Reason-gated in_progress→blocked transition (evaluate_blocked, warn-first) + blocker taxonomy

**Outcome (one sentence):** An in_progress→blocked transition requires a concrete blocker reason (validated by a new evaluate_blocked, warn-first then COS_BLOCKED_STRICT) tagged with a blocker taxonomy (external/dependency/decision/quota), so a parked task can never become a reasonless black hole — mirroring the DoR/DoD reason discipline.

## Read First
- src/core/board_os/transition_gates_validator.py
- src/core/board_os/transition_gates_cli.py
- src/core/board_os/workflow.py
- src/core/board_os/mcp_tools.py
- docs/governance/task-lifecycle.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a →blocked move with an empty or placeholder reason, **When** evaluate_blocked runs in warn mode, **Then** it WARNs (and BLOCKs under COS_BLOCKED_STRICT=1).
- **Given** a →blocked move with a concrete reason plus a taxonomy tag, **When** it runs, **Then** it passes and the taxonomy is persisted on the task.
- **Given** the warn-first rollout, **When** existing callers move tasks to blocked without a tag, **Then** nothing hard-breaks (backward compatible).

## Implementation Guards (verified wiring)
- evaluate_blocked fires on the live path ONLY if "blocked" is added to BOTH cmd_check_payload's status set (transition_gates_cli.py:210 `{in_progress, complete}`) AND workflow.py's gate condition (`to_status in {"in_progress","complete"}`, ~:531). Without both, the new gate is dead code — wire both, warn-first.

## Work Log
