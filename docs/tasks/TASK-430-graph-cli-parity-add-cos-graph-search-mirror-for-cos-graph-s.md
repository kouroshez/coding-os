---
id: TASK-430
title: "Graph CLI parity: add `cos graph-search` mirror for cos_graph_search MCP tool (test_graph_cli_parity failing)"
swimlane: infra
kind: bug
epic: null
labels: [graph, parity, tech-debt, ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-15
started: 2026-06-16
completed: 2026-06-16
agent_session: ses-803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-430: Graph CLI parity: add `cos graph-search` mirror for cos_graph_search MCP tool (test_graph_cli_parity failing)

**Outcome (one sentence):** Restore 21/21 (now 22/22) graph MCP↔CLI parity. Commit 5503d456 added the cos_graph_search MCP tool (sqlite-vec hybrid ANN) but no `cos graph-search` CLI command, so test_graph_cli_parity::test_every_mcp_graph_tool_has_cli_command fails. Add the CLI mirror in src/cli/graph_commands.py delegating to the same tool.

## Read First
- src/cli/graph_commands.py
- src/core/graph_os/tools/graph.py
- tests/test_graph_cli_parity.py

## Repro Steps
uv run pytest tests/test_graph_cli_parity.py::test_every_mcp_graph_tool_has_cli_command -q → AssertionError: MCP graph tools missing a `cos {cmd}` CLI mirror: ['graph-search'].

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the cos_graph_search MCP tool exists **When** `cos graph-search <query>` runs **Then** it returns the same hybrid-ANN results envelope as the MCP tool. - **When** test_graph_cli_parity runs **Then** it passes (every MCP graph tool has a CLI mirror).

## Work Log
- 2026-06-16 [claude]: Edit graph_commands.py
- 2026-06-16 [ses-803-0b9f]: Added `cos graph-search` CLI mirror in graph_commands.py (delegates to cos_graph_search, top_k flag, same envelope via _
