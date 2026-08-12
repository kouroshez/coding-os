---
id: TASK-946
title: "feat: manage Codex MCP servers from the Hub without destroying the TOML file"
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
# TASK-946: feat: manage Codex MCP servers from the Hub without destroying the TOML file

**Outcome (one sentence):** A user adds or removes an MCP server for the Codex adapter from the Hub, and the resulting ~/.codex/config.toml keeps every comment, key order, and unrelated table the user had written by hand.

## Read First
- src/core/web/routes/_config_mcp.py
- src/adapters/codex/adapter.yaml
- docs/engineering/hub-architecture.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a hand-maintained ~/.codex/config.toml with comments **When** the Hub adds an MCP server **Then** the file gains one [mcp_servers.name] table and every pre-existing comment and table survives byte-identical. **Given** Python 3.10 **When** the writer runs **Then** it works without tomllib, or the dependency it needs is declared and justified. **Given** the Hub MCP view **When** Codex is an installed adapter **Then** its servers are listed alongside the Claude ones rather than reported as unmanaged.

## Work Log
- 2026-08-12 [claude]: Delivered with TASK-944: append + span-delete line editor, no tomllib and no new dep; 14 tests green on…
- 2026-08-12 [claude]: Status transitioned to complete via cos task-done.
