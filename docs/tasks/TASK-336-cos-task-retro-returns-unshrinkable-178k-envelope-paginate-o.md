---
id: TASK-336
title: "cos_task_retro returns unshrinkable 178k envelope \u2014 paginate or summarize within the 32k budget"
swimlane: "board_os"
kind: bug
epic: null
labels: [ready]
status: testing
priority: P2
appetite: 1d
created: 2026-06-10
started: 2026-06-10
completed: null
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-336: cos_task_retro returns unshrinkable 178k envelope — paginate or summarize within the 32k budget

**Outcome (one sentence):** `cos_task_retro` (and the `cos retro` CLI) returns a digest that fits the 32k envelope budget — aggregated counts + top-N highlights with a cursor for the long tail — instead of dumping every completed card (observed 178,284 chars > 32,000 on 2026-06-10 after ~270 completions; safe_tool flagged it `envelope_unshrinkable`).

## Read First
- src/core/board_os/mcp_tools.py (cos_task_retro — the dump site)
- src/core/thinking_os/tools/_shared.py (ok() token-budget trimmer + unshrinkable flag)
- src/core/board_os/mcp_tools.py::cos_task_board (keyset pagination pattern to reuse — Rule 22)

## Repro Steps
1. On a board with hundreds of completed tasks (this repo), run `cos retro`.
2. Observe stderr: `tool cos_task_retro returned an unshrinkable envelope (178284 chars > 32000 budget)` and a flood of full card bodies.
Expected: a bounded retro digest (counts by swimlane/kind, cycle-time stats, top highlights) + cursor for more.
Actual: every completed card serialized whole; the envelope trimmer cannot shrink it.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a board with 300+ completed tasks
- **When** `cos_task_retro` runs with defaults
- **Then** the envelope is under the 32k budget, carries aggregate stats + top-N items, and sets meta.truncated/cursor for the tail — no unshrinkable log line
- **Given** the existing board pagination pattern
- **When** the fix lands
- **Then** it reuses the keyset-cursor approach from cos_task_board (no second pagination scheme), covered by a board_os test asserting envelope size on a seeded 300-task DB

## Work Log
- 2026-06-10 [claude]: Implementation designed and dry-fitted, then cleanly reverted: cos_task_retro → whole-window aggregates via slim project
- 2026-06-10 [claude]: Shipped (score 9/10): cos_task_retro now returns whole-window aggregates via slim projection + a keyset-paginated lean h
