---
id: TASK-324
title: "Hub: live-agent context_pct on dashboard \u2014 consume /api/presence/agents per hub-architecture spec"
swimlane: core
kind: feature
epic: null
labels: [hub-ui, spec-drift, audit-2026-06-09, ready]
status: icebox
priority: P3
appetite: 1d
created: 2026-06-10
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-324: Hub: live-agent context_pct on dashboard — consume /api/presence/agents per hub-architecture spec

**Outcome (one sentence):** The dashboard shows each live agent's context-window fill (context_pct) from the already-implemented /api/presence/agents route — closing the documented spec-vs-reality gap (hub-architecture.md specs it, presence.py computes it, no UI consumes it).

## Read First
- docs/engineering/hub-architecture.md (the spec — context_pct contract)
- src/core/board_os/presence.py (_context_pct producer — exact field names)
- src/core/web/ui/src/pages/DashboardPage.tsx (today reads /api/sessions/active)
- src/core/rules/api-contract-discipline.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** ≥1 live agent session with presence data
- **When** the dashboard renders
- **Then** each agent row shows context_pct from /api/presence/agents, field names verified against presence.py's emit
- **Given** an agent with no context signal
- **When** the row renders
- **Then** it shows an explicit unknown state (not 0%, not blank)
- **Given** hub-architecture.md
- **When** the feature ships
- **Then** the spec row flips to implemented (doc and code stay in sync — Rule 19)

## Work Log
