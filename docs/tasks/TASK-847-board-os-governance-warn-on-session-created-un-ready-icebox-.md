---
id: TASK-847
title: "board_os governance: warn on session-created un-ready icebox cards (create-then-park nudge)"
swimlane: "board_os"
kind: feature
epic: null
labels: []
status: complete
priority: P2
appetite: 1d
created: 2026-07-18
started: 2026-07-18
completed: 2026-07-17
agent_session: ses-claude-20260717-131858-7098
depends_on: []
blocked_by: []
references: []
---
# TASK-847: board_os governance: warn on session-created un-ready icebox cards (create-then-park nudge)

**Outcome (one sentence):** warn-abandoned-task.sh (Stop hook) also warns when the current session created an icebox card left un-ready and un-parked at turn-end, attributing via the EXISTING task_status_history 'created' row (no new schema column) — closing the create-then-park enforcement blind spot (deep-research report §6).

## Read First
- src/core/hooks/warn-abandoned-task.sh
- docs/governance/task-lifecycle.md (Execution Rules — the sibling 'Aging blockers surface' nudge)
- src/core/board_os/mcp_tools.py:797 (the create-history row that already records the creating session)

## Acceptance (G/W/T) — *this IS the Definition of Done*
1. **Given** the current session created an icebox card carrying no ready/parked/keep label, **When** the Stop hook fires at turn-end, **Then** the hook warns and names that task id.
2. **Given** the session-created icebox card is labeled ready (or parked/keep), **When** the Stop hook fires, **Then** that card is NOT included in the create-then-park warning (deliberate queue/defer is exempt).
3. **Given** the session created no un-ready icebox cards, **When** the Stop hook fires with otherwise-clean state, **Then** no create-then-park warning is emitted.

## Work Log
- 2026-07-18 [claude]: Edit task-lifecycle.md
- 2026-07-18 [claude]: Edit warn-abandoned-task.sh
- 2026-07-18 [claude]: Edit warn-abandoned-task.sh
- 2026-07-18 [claude]: Edit test_warn_abandoned_task.py
- 2026-07-18 [claude]: Reuse-first pivot (honors P1 SSOT over the report's literal QW-3): graph+read showed cos_task_create already writes a…
- 2026-07-18 [claude]: committed 74c684ef · 11 files
