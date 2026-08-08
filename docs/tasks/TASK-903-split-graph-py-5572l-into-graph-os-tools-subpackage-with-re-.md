---
id: TASK-903
title: "Split graph.py (5572L) into graph_os tools subpackage with re-exported cos_graph_* surface"
swimlane: core
kind: refactor
epic: null
labels: [graph, god-file, ready]
status: icebox
priority: P2
appetite: 3d
created: 2026-08-08
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-903: Split graph.py (5572L) into graph_os tools subpackage with re-exported cos_graph_* surface

**Outcome (one sentence):** graph.py decomposed into cohesive modules; tool names + envelopes unchanged; ratchet MAX lowered

## Read First
- docs/engineering/graph_os-queries.md
- docs/governance/mcp-tool-inventory.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the graph_os test suite and MCP self-test\n- **When** graph.py is split into a subpackage re-exporting all cos_graph_* tools\n- **Then** uv run --extra graph_os pytest src/core/graph_os/tests/ -q passes and python src/core/thinking_os/server.py --test registers the same tool inventory

## Work Log
