---
id: TASK-576
title: "Cluster 3 \u2014 Graph tool usability so the graph beats grep: fix lying references count, expose impact visit_limit, reconcile confidence_min, dead_code FPs, one coverage object"
swimlane: "graph_os"
kind: refactor
epic: graph-first-enforcement
labels: [graph, tool-usability, api-contract, graph-gate, ready]
status: icebox
priority: P2
appetite: 1d
created: 2026-06-25
started: null
completed: null
agent_session: null
depends_on: [TASK-573]
blocked_by: []
references: []
---

# TASK-576: Cluster 3 — Graph tool usability so the graph beats grep: fix lying references count, expose impact visit_limit, reconcile confidence_min, dead_code FPs, one coverage object

**Outcome (one sentence):** references count no longer lies (recompute in the trimmer or drop in favour of total_count + array len) and exposes a coverage signal so the agent knows the inbound set is incomplete; cos_graph_impact exposes visit_limit in the MCP schema (matching the HTTP route's 1..50000) and reconciles confidence_min default 0.3 vs 0.5; impact tiers carry per-bucket totals (will_break_total); dead_code stops false-positiving exception classes, PEP604 X|None field-types, and factory/dynamic-dispatch classes; one coverage object {complete,returned,total,reason} replaces the 3 disagreeing truncation signals. Closes N5, N6, N12, N13, SM3.

## Read First
- src/core/graph_os/tools/graph.py
- src/core/graph_os/tools/_shared.py
- src/core/thinking_os/server.py
- src/core/web/routes/graph.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
GIVEN a 110-edge hub WHEN references is called THEN count == array length and a coverage/incomplete flag is set (no silent lie); GIVEN cos_graph_impact via MCP THEN visit_limit is an accepted arg and confidence_min matches the HTTP route; GIVEN a caught-but-never-constructed exception class THEN dead_code does NOT flag it; AND graph_os matrix suite green; AND thinking_os server --test passes.

## Work Log
