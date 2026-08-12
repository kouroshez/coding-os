---
id: TASK-944
title: "feat: Hub manages MCP servers with scope and per-adapter targeting"
swimlane: core
kind: feature
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-08-12
started: 2026-08-12
completed: 2026-08-12
agent_session: ses-claude-20260807-224955-abc1
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
- 2026-08-12 [claude]: Live inventory 1 -> 9 servers across claude+codex, project+global, stdio+http; codex round-trip on the real config is…
- 2026-08-12 [claude]: Status transitioned to complete via cos task-done.
