---
id: TASK-192
title: "Live context-window percent per Claude agent honest N/A for others"
swimlane: core
kind: feature
epic: agent-hub
labels: [ready]
status: archive
priority: P3
appetite: "4h"
created: 2026-06-06
started: 2026-06-05
completed: 2026-06-05
agent_session: ses-claude-20260605-183120-db30
depends_on: []
blocked_by: []
references: []
---
# TASK-192: Live context-window percent per Claude agent honest N/A for others

**Outcome (one sentence):** The unified live-agent snapshot carries a context_pct for Claude agents (derived from the latest SDK transcript usage joined via sdk_uuid) and null/N-A for adapters with no usage signal — never a fabricated number.

## Read First
- docs/engineering/agent-hub-orchestration.md
- src/core/web/routes/cognition.py
- src/core/web/routes/presence.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a Claude agent with a known sdk_uuid and a transcript carrying usage
- **When** GET /api/presence/agents is called
- **Then** the agent row includes context_pct in [0,100] computed from input+cache tokens over the model's window (1M for [1m], else 200K); agents with no sdk_uuid/usage get context_pct=null; the HUD shows the percent or N/A. A pure-function test covers the percent math; tsc + ui-build green.

## Work Log
- 2026-06-06 [claude]: /api/presence/agents now adds context_pct: tails the in-tree transcript snapshot for the latest usage (cheap, no SDK cal
