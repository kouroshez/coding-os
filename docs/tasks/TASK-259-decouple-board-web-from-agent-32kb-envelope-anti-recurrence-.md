---
id: TASK-259
title: "Decouple board/web from agent 32KB envelope + anti-recurrence guard"
swimlane: core
kind: bug
epic: hub-redesign
labels: [envelope, board, scale, ready]
status: archive
priority: P1
appetite: 1d
created: 2026-06-08
started: 2026-06-08
completed: 2026-06-08
agent_session: ses-claude-20260608-021813-db02
depends_on: []
blocked_by: []
references: []
---
# TASK-259: Decouple board/web from agent 32KB envelope + anti-recurrence guard

**Outcome (one sentence):** Fix the recurring `cos_task_board returned an unshrinkable envelope (186574 > 32000)` error at its architectural root — add a budget opt-out to ok(), thread it through the browser board path, drop the duplicated `grouped` field, sweep sibling wide-payload tools into the trim ladder, and add an anti-recurrence contract test.

## Read First
- /tmp/cos-board-envelope-and-hub-plan.md (EPIC A = STEP 1,2,3,11,13 + §13 review)
- src/core/thinking_os/tools/_shared.py (ok(), _apply_token_budget, _TRIMMABLE_LIST_KEYS)
- src/core/board_os/mcp_tools.py (cos_task_board, _cap_board_to_budget)

## Repro Steps
1. Open the Hub board (`/api/board/list`) on a project with many active tasks (>~135 active cards, or include_archive over a full page).
2. Watch the hub log while the board renders.
Expected: board renders, no error.
Actual: `tool cos_task_board returned an unshrinkable envelope (186574 chars > 32000 budget)` logged at ERROR — the 32KB agent cap leaks onto the browser path.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a board whose serialized payload exceeds 32KB requested via the browser path (`apply_budget=False`),
- **When** `cos_task_board` returns through `ok()`,
- **Then** the response is NOT trimmed, sets no `envelope_unshrinkable`, and logs no ERROR; the agent path (default budget) still caps at 32KB; the duplicated `grouped` field is gone; and a contract test proves no real `cos_*` tool can silently emit `envelope_unshrinkable`.

## Work Log
- 2026-06-08 [claude]: S1+S2 done (commit 17445116): ok() now honors apply_budget=False (web opt-out), cos_task_board threads it; doc updated (
- 2026-06-08 [claude]: EPIC A complete. S11+S13 (c8b94a98): added rows/entries/cycles/untested/dead to _TRIMMABLE_LIST_KEYS + parametrized cove
