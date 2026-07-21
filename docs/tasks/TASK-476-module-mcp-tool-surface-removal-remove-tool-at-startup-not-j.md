---
id: TASK-476
title: "Module\u2192MCP-tool surface removal \u2014 remove_tool at startup, not just runtime fail (module-bundle: tools dimension)"
swimlane: infra
kind: feature
epic: null
labels: [modularity, mcp, audit-pass4, ready]
status: archive
priority: P2
appetite: 1d
created: 2026-06-20
started: 2026-06-20
completed: 2026-06-20
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-476: Module→MCP-tool surface removal — remove_tool at startup, not just runtime fail (module-bundle: tools dimension)

**Outcome (one sentence):** A disabled module's MCP tools DISAPPEAR from the agent's live tool list at server startup via FastMCP `mcp.remove_tool(name)`, so the agent never sees or hallucinates them — converting today's call-time `fail('module_disabled')` gate (tool still advertised, errors when called) into true surface removal ("as if the module never existed"). The per-call `safe_tool` gate stays as defense-in-depth for clients with a cached tool list or a mid-session toggle. Per-project (server reads $COS_STATE_DIR/subsystems-state.json), fail-open. On the existing map this immediately sheds 55/90 tools (graph 22, tasks 21, memory 9, docs 3) when those modules are off.

## Read First
- src/core/thinking_os/tools/_shared.py
- src/core/thinking_os/server.py
- src/core/subsystems.yaml

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a project with `graph` disabled in subsystems-state.json **When** `cos server-start` boots the stdio server **Then** `mcp._tool_manager.list_tools()` contains zero `cos_graph_*` tools and all kernel + other-module tools remain.
**Given** no modules disabled **When** the server boots **Then** the served tool surface is byte-identical to today (zero regression for the default all-on consumer).
**Given** subsystems-state.json missing/corrupt **When** the server boots **Then** the FULL surface is served (fail-open) with a debug breadcrumb — never a half-surface.
**Given** `python server.py --test` **Then** the full set still registers (surface removal applies only on the stdio serve path, so the self-test's registration assertions stay green).

## Work Log
- 2026-06-20 [claude]: Edit modularity-audit-2026-06.md
- 2026-06-20 [claude]: Edit _shared.py
- 2026-06-20 [claude]: Edit server.py
- 2026-06-20 [claude]: Edit server.py
- 2026-06-20 [claude]: Edit test_module_gating.py
- 2026-06-20 [claude]: Edit test_module_gating.py
- 2026-06-20 [claude]: Edit verify_476.py
- 2026-06-20 [claude]: Implemented apply_module_tool_gating in tools/_shared.py + wired into server.main() stdio branch (full set kept on…
- 2026-06-20 [claude]: commit 6595c6e7e7 — feat(modularity): MCP tool surface-removal on module disable (remove_tool at startup)
- 2026-06-20 [claude]: Status transitioned to complete via cos task-done.
