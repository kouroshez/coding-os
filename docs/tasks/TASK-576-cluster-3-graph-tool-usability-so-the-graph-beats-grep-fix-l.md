---
id: TASK-576
title: "Cluster 3 \u2014 Graph tool usability so the graph beats grep: fix lying references count, expose impact visit_limit, reconcile confidence_min, dead_code FPs, one coverage object"
swimlane: "graph_os"
kind: refactor
epic: graph-first-enforcement
labels: [graph, tool-usability, api-contract, graph-gate, ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-25
started: 2026-06-25
completed: 2026-06-25
agent_session: ses-claude-20260625-122147-96fb
depends_on: [TASK-573]
blocked_by: []
references: []
---
# TASK-576: Cluster 3 — Graph tool usability so the graph beats grep: fix lying references count, expose impact visit_limit, reconcile confidence_min, dead_code FPs, one coverage object

**Outcome (one sentence):** references count no longer lies (recompute after trim so count == array length) and carries a coverage signal; cos_graph_impact exposes visit_limit in the MCP schema (matching the HTTP route's 1..50000) and reconciles confidence_min; impact/references/detect_changes envelopes gain the meta.stale freshness field folded from C1; dead_code stops false-positiving caught-but-never-constructed exception classes; a unified coverage object is added (non-breaking) alongside the existing truncation signals. Closes N5, N6, N12, N13, SM3 + D2 (impact/references/detect_changes envelopes).

## Read First
- src/core/graph_os/tools/graph.py
- src/core/graph_os/tools/_shared.py
- src/core/thinking_os/server.py
- src/core/web/routes/graph.py

## Acceptance (G/W/T) — *this IS the Definition of Done*

**Given** a hub whose inbound edge set is trimmed, **When** cos_graph_references is called, **Then** data.count == len(the returned array) (no silent lie) and a coverage/incomplete flag is set.

**Given** cos_graph_impact called via MCP, **When** visit_limit is passed, **Then** it is an accepted arg (schema matches the HTTP route's 1..50000) and confidence_min default is reconciled with the HTTP route.

**Given** a caught-but-never-constructed exception class, **When** dead_code runs, **Then** it does NOT flag it; **And** impact/references/detect_changes surface meta.stale freshness.

**Then** the graph_os matrix suite is green; **And** `python src/core/thinking_os/server.py --test` passes.

## Work Log
- 2026-06-25 [claude]: Scope add (folded from C1/TASK-574 for cohesion): add meta.stale/freshness field (disk content_hash vs file_index_state) to cos_graph_impact / cos_graph_references / cos_graph_detect_changes envelopes — joins the one-coverage-object work. cos_graph_context already ships it in C1.
- 2026-06-25 [claude]: Edit server.py
- 2026-06-25 [claude]: Edit _shared.py
- 2026-06-25 [claude]: Edit graph.py
- 2026-06-25 [claude]: Edit graph.py
- 2026-06-25 [claude]: Edit graph.py
- 2026-06-25 [claude]: Edit graph.py
- 2026-06-25 [claude]: Edit graph.py
- 2026-06-25 [claude]: Edit test_mcp_tools.py
- 2026-06-25 [claude]: Edit SKILL.md
- 2026-06-25 [claude]: Landed: N5 — trimmer reconciles a sibling `count` post-trim when it tracked the trimmed list's original length…
