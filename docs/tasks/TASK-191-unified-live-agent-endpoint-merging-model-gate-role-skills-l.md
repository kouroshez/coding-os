---
id: TASK-191
title: "Unified live-agent endpoint merging model gate role skills lifecycle + clickable detail"
swimlane: core
kind: feature
epic: agent-hub
labels: [ready]
status: archive
priority: P2
appetite: "1d"
created: 2026-06-06
started: 2026-06-05
completed: 2026-06-05
agent_session: ses-claude-20260605-183120-db30
depends_on: []
blocked_by: []
references: []
---
# TASK-191: Unified live-agent endpoint merging model gate role skills lifecycle + clickable detail

**Outcome (one sentence):** One GET /api/presence/agents returns, per agent, model+gate+task+skill+role+chain+lifecycle (+sdk_uuid) in a single call by reusing the existing readers; the Live HUD makes each agent clickable to a live detail popup.

## Read First
- docs/engineering/agent-hub-orchestration.md
- src/core/web/routes/presence.py
- src/core/web/routes/roles.py
- src/core/web/ui/src/layout/LiveStatus.tsx

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** one or more live agents
- **When** the UI calls GET /api/presence/agents
- **Then** it returns one row per agent with model, gate, task, skill_active, role, chain, lifecycle state and sdk_uuid (all read live from the same SSOT readers as /presence/now + /roles/chain + board_os.presence); the Live HUD makes each agent clickable to a detail popup. Route test + make ui-build green.

## Work Log
- 2026-06-06 [claude]: Added GET /api/presence/agents unifying model+gate+task+skill+role+chain+lifecycle+sdk_uuid per agent by reusing _agent_
