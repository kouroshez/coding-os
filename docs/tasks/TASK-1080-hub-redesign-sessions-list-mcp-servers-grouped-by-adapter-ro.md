---
id: TASK-1080
title: "Hub redesign: Sessions list, MCP servers grouped by adapter, Roles roster"
swimlane: core
kind: feature
epic: null
labels: [docs-update, hub, ready]
status: complete
priority: P2
appetite: 1d
created: 2026-10-25
started: 2026-10-24
completed: 2026-10-24
agent_session: ses-claude-20261024-131905-031f
depends_on: []
blocked_by: []
references: []
---
# TASK-1080: Hub redesign: Sessions list, MCP servers grouped by adapter, Roles roster

**Outcome (one sentence):** Sessions, Config › MCP Servers and Config › Roles read as clean, scannable lists: sessions without trace leftovers, each MCP server listed once with the adapters that load it, and roles as a roster with the active chain.

## Read First
- docs/engineering/hub-architecture.md
- src/core/web/ui/src/pages/SessionsPage.tsx
- src/core/web/ui/src/features/config/McpTab.tsx
- src/core/web/ui/src/pages/RolesPage.tsx

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the Sessions page, **When** it renders, **Then** live sessions show agent, model, state, context and activity, and no copy or column mentions traces.
- **Given** an MCP server configured for both claude and codex, **When** the MCP tab renders, **Then** it appears once with both adapters named, and its command line is truncated with the full text available.
- **Given** Config › Roles, **When** it renders, **Then** the roster, the active chain and the evidence panel use the Hub card styling and never sit on a permanent loading line.

## Work Log
- 2026-10-25 [claude]: Mobbin refs Twingate/Tailscale (filterable connector tables) + Customer.io integrations. Found and fixed a real bug:…
- 2026-10-25 [claude]: Status transitioned to complete via cos task-done.
