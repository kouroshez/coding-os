---
id: TASK-220
title: "Board UI truncated to ~14 cards \u2014 cos_task_board applies the agent 32KB token budget to the web route; decouple browser path + lean cards"
swimlane: "board_os"
kind: bug
epic: null
labels: [board, web, hub, ui, performance, ready]
status: archive
priority: P1
appetite: 1d
created: 2026-06-07
started: 2026-06-06
completed: 2026-06-06
agent_session: ses-claude-20260606-135311-dd32
depends_on: []
blocked_by: []
references: []
---
# TASK-220: Board UI truncated to ~14 cards — cos_task_board applies the agent 32KB token budget to the web route; decouple browser path + lean cards

**Outcome (one sentence):** The web board shows ALL tasks per column (not a 14-card slice): cos_task_board's 32KB MCP token-budget cap is an agent-context guard and must NOT apply to the browser route, which is not token-limited. board_list passes apply_budget=False and a board-sized limit so the kanban renders every card; the agent/MCP path keeps the budgeted, complete/archive-excluded default. Verified by the web board returning the full set and no 'unshrinkable envelope' error on the browser path.

## Read First
- src/core/board_os/mcp_tools.py
- src/core/web/routes/board.py
- docs/engineering/hub-architecture.md

## Repro Steps
1. With ~219 tasks in the DB (191 complete), open the Hub web board (Workspace → Board) which fetches `/api/board/list?include_archive=true`.
2. The route calls `cos_task_board`, which caps the envelope to `TOKEN_BUDGET_CHARS` (32KB) via `_cap_board_to_budget`.
Expected: every card renders per column (full COMPLETE column).
Actual: only ~14 cards render; hub.log shows `cos_task_board returned an unshrinkable envelope (398520 chars > 32000 budget)` — the agent token-budget cap truncates the browser's board.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the board has more cards than fit in the 32KB MCP token budget (e.g. 191 complete tasks).
- **When** the browser fetches the board via `/api/board/list` (which calls `cos_task_board` with `apply_budget=False`).
- **Then** the response contains every card (cards == total_count, truncated=false) with no 'unshrinkable envelope' error, while a direct MCP `cos_task_board` call (apply_budget defaulting True) still caps to the budget for agent context.

## Work Log
- 2026-06-07 [claude]: Root cause: web board_list called cos_task_board which applies the 32KB MCP token-budget cap (_cap_board_to_budget) — an
- 2026-06-07 [claude]: committed ebb8fd76: src/core/board_os/mcp_tools.py, src/core/web/routes/board.py
