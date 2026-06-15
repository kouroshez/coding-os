---
id: TASK-430
title: "Graph CLI parity: add `cos graph-search` mirror for cos_graph_search MCP tool (test_graph_cli_parity failing)"
swimlane: infra
kind: bug
epic: null
labels: [graph, parity, tech-debt, ready]
status: icebox
priority: P2
appetite: 1d
created: 2026-06-15
started: null
completed: null
agent_session: null
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
