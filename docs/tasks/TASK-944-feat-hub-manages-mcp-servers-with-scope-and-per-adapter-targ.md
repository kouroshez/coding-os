---
id: TASK-944
title: "feat: Hub manages MCP servers with scope and per-adapter targeting"
swimlane: core
kind: feature
epic: null
labels: [ready]
status: icebox
priority: P2
appetite: 1d
created: 2026-08-12
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-944: feat: Hub manages MCP servers with scope and per-adapter targeting

**Outcome (one sentence):** From the Hub a user can see every MCP server the machine and the project actually declare, add one to a chosen scope and chosen adapters, and pick from a curated recommended list in one click.

## Read First
- src/core/web/routes/config.py
- src/core/web/routes/_config_read.py
- src/core/web/routes/_config_mutate.py
- docs/engineering/hub-architecture.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a machine with global and project MCP configs **When** the Hub MCP view loads **Then** it lists both, labelled by scope, including HTTP and SSE transports. **Given** the user adds a server **When** they choose scope and adapters **Then** each selected adapter config is written in that adapter's own format and the others are untouched. **Given** the recommended list **When** the user clicks add **Then** the server lands in the chosen scope without hand-editing JSON.

## Work Log
