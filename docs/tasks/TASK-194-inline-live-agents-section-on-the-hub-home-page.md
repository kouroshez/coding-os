---
id: TASK-194
title: "Inline live-agents section on the hub home page"
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
# TASK-194: Inline live-agents section on the hub home page

**Outcome (one sentence):** The home page surfaces a live-agents panel inline (not only the AppShell popover), using the unified /api/presence/agents endpoint, with each agent showing model/gate/role/state/context and a click-through to its cognition detail.

## Read First
- docs/engineering/agent-hub-orchestration.md
- src/core/web/ui/src/pages/HubHome.tsx
- src/core/web/ui/src/layout/LiveStatus.tsx

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** live agents present on the project
- **When** the user opens the home page
- **Then** an inline live-agents section lists each agent with model/gate/role/state/context (from /api/presence/agents) and links to its chat/cognition detail; renders nothing/empty-state when no agents; make ui-build green.

## Work Log
- 2026-06-06 [claude]: New LiveAgentsPanel renders inline on the home page from /api/presence/agents — one card per live (non-offline) agent wi
