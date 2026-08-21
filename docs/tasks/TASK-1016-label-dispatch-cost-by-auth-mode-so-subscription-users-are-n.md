---
id: TASK-1016
title: "Label dispatch cost by auth mode so subscription users are not shown fictional spend"
swimlane: "thinking_os"
kind: bug
epic: null
labels: [supervision, hub, observability, ready]
status: complete
priority: P2
appetite: 1d
created: 2026-08-21
started: 2026-08-20
completed: 2026-08-20
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-1016: Label dispatch cost by auth mode so subscription users are not shown fictional spend

**Outcome (one sentence):** The dispatch cost rollup states which auth mode produced its numbers, so a subscription operator reads them as notional API-equivalent rather than money spent, while an API operator still gets real spend.

## Read First
- src/core/web/routes/cognition_dispatch_views.py
- src/adapters/claude/_claude_sdk_options.py
- docs/engineering/agent-supervision.md

## Repro Steps
1. `.coding-os/hub-settings.json` carries `claude_auth.mode = "subscription"` for this project. 2. The Claude SDK still reports `total_cost_usd` — the API-equivalent price of the tokens, not a charge. 3. `/api/cognition/cost` and the Hub CostPanel present that figure as spend, so the operator was shown "$1.1294" for work that cost them nothing beyond subscription quota. 4. The auth mode is already known to the code (`_claude_auth_env` reads it) but is not carried into the cost payload.

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a project whose `claude_auth.mode` is `subscription`
**When** /api/cognition/cost is queried
**Then** the payload names the auth mode so the consumer can label the figure notional rather than spent.

**Given** a project on `api_key`
**When** the same query runs
**Then** the mode is reported as api_key and the figure stands as real spend.

**Given** the Hub CostPanel
**When** it renders under a subscription
**Then** the total is not presented as money spent.

## Work Log
- 2026-08-21 [claude]: The cost split I shipped one turn earlier was misleading for this operator: claude_auth.mode is `subscription`, so…
- 2026-08-21 [claude]: Status transitioned to complete via cos task-done.
