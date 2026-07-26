---
id: TASK-583
title: "Make Codex MCP config project-local and self-contained"
swimlane: adapters
kind: chore
epic: null
labels: [codex, mcp, project-config, ready]
status: archive
priority: P2
appetite: 1d
created: 2026-06-26
started: 2026-06-25
completed: 2026-06-25
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-583: Make Codex MCP config project-local and self-contained

**Outcome (one sentence):** Codex loads the coding-os MCP from this repository's project config without relying on global MCP settings.

## Work Log
- 2026-06-26 [claude]: Verified project-local Codex MCP config exists; preparing self-contained project feature flag update.
- 2026-06-26 [claude]: Verified `codex mcp get coding-os`, `codex mcp list`, `uv run python src/core/thinking_os/server.py --test`, and `cos health`.
- 2026-06-26 [claude]: Status transitioned to complete via cos task-done.
