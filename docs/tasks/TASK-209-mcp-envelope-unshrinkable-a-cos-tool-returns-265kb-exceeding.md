---
id: TASK-209
title: "MCP envelope unshrinkable \u2014 a cos_ tool returns 265KB exceeding 32KB budget, floods the eye with ERROR"
swimlane: "thinking_os"
kind: bug
epic: null
labels: [mcp, envelope, observability, ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-06
started: 2026-06-06
completed: 2026-06-06
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-209: MCP envelope unshrinkable — a cos_ tool returns 265KB exceeding 32KB budget, floods the eye with ERROR

**Outcome (one sentence):** The MCP tool that returns a 265KB unshrinkable envelope is identified (cos_task_board — it returns `grouped` + `cards` as the same cards twice, and neither is in the envelope trim ladder) and capped so it fits the 32KB budget; cos doctor runtime.recent_errors stops accruing the envelope-unshrinkable fingerprint. Guarded by a test.

## Read First
- src/core/thinking_os/tools/_shared.py
- src/core/board_os/mcp_tools.py
- docs/engineering/mcp-error-envelope.md

## Repro Steps
1. Run `cos_task_board` on a project with many tasks (e.g. status_filter=["icebox"] with ~29 cards, or the full board) via the MCP tool.
2. Inspect `data.meta`: `truncated=true` AND `envelope_unshrinkable=true`, serialized envelope far exceeds TOKEN_BUDGET_CHARS (32KB) — observed ~54KB for 29 cards, ~265KB for a large board.
Expected: the board envelope fits 32KB (capped, with a truncation signal) and safe_tool logs no envelope-unshrinkable ERROR.
Actual: the response is unshrinkable (grouped is a nested dict + cards duplicates it; neither is in `_TRIMMABLE_LIST_KEYS`), so safe_tool re-logs ERROR every call, flooding cos doctor runtime.recent_errors.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a project whose board would serialize over the 32KB envelope budget
- **When** cos_task_board is called (MCP or Hub route)
- **Then** the returned envelope fits TOKEN_BUDGET_CHARS, carries `total_count` + `truncated=true` when cards were dropped, keeps `grouped` and `cards` consistent, and meta.envelope_unshrinkable is never set for the board — guarded by a board-budget test in board_os tests.

## Work Log
- 2026-06-06 [claude]: Diagnosability done (commit 6f1cab46): safe_tool now names the tool on unshrinkable envelope; 1335+38 tests green.
- 2026-06-06 [claude]: Identified culprit = cos_task_board (returns grouped + cards = same cards twice, neither in the envelope trim ladder → u
- 2026-06-06 [claude]: committed 3575051f: src/core/board_os/mcp_tools.py, src/core/board_os/tests/test_mcp_tools.py
