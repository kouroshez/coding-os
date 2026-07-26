---
id: TASK-574
title: "Cluster 1 \u2014 Make the graph-gate marker contract real: MCP-written, freshness-bound, panel-scoped + GC, with producer-side round-trip test"
swimlane: "graph_os"
kind: refactor
epic: graph-first-enforcement
labels: [graph, hooks, marker-contract, freshness, graph-gate, ready]
status: archive
priority: P1
appetite: 1d
created: 2026-06-25
started: 2026-06-25
completed: 2026-06-25
agent_session: ses-system-auto-archive
depends_on: [TASK-573]
blocked_by: []
references: []
---
# TASK-574: Cluster 1 — Make the graph-gate marker contract real: MCP-written, freshness-bound, panel-scoped + GC, with producer-side round-trip test

**Outcome (one sentence):** cos_graph_context/cos_graph_rename_plan write per-target markers themselves (extend _touch_session_marker) embedding the target's content_hash + index epoch, into one $COS_PANEL_DIR/.graph/ namespace; the enforce hooks stop telling the agent to hand-run write-state.sh; markers invalidate when disk content_hash != recorded; markers are added to the panel-scoped GC sweep. impact/context/detect_changes/references envelopes gain a freshness field (disk hash vs file_index_state). Closes A1, A2, D2, C3, C4, SM1, SM2.

## Read First
- src/core/graph_os/tools/graph.py
- src/core/hooks/enforce-graph-context.sh
- src/core/hooks/enforce-rename-plan.sh
- src/core/hooks/cos-env.sh
- src/core/graph_os/tests/test_i14_hooks.py

## Acceptance (G/W/T) — *this IS the Definition of Done*

**Given** a real `cos_graph_context(target)` call, **When** the agent then edits `target`, **Then** the enforce hook passes WITHOUT any hand-written marker — a producer-side round-trip test asserts the MCP call itself wrote `.graph/ctx-<sha>`.

**Given** the file content changed on disk since the consult, **When** the agent edits it, **Then** the recorded marker is treated as stale (disk content_hash != recorded) and the hook re-warns.

**Given** session/panel end, **When** the GC sweep runs, **Then** the `.graph/` markers are reaped alongside the other panel-scoped state.

**Given** a graph read whose disk hash differs from file_index_state, **When** the envelope is returned, **Then** `meta.stale=true` surfaces the staleness; **And** the `graph_os` matrix suite is green.

## Work Log
- 2026-06-25 [claude]: Edit graph.py
- 2026-06-25 [claude]: Edit graph.py
- 2026-06-25 [claude]: Edit graph.py
- 2026-06-25 [claude]: Edit graph_marker_check.py
- 2026-06-25 [claude]: Edit enforce-graph-context.sh
- 2026-06-25 [claude]: Edit enforce-rename-plan.sh
- 2026-06-25 [claude]: Edit session-context.sh
- 2026-06-25 [claude]: Edit test_mcp_tools.py
- 2026-06-25 [claude]: Edit test_i14_hooks.py
- 2026-06-25 [claude]: Edit test_i14_hooks.py
- 2026-06-25 [claude]: Edit 0014-unified-graph-gate-enforced-dependency-check-before-edit.md
- 2026-06-25 [claude]: Edit 0014-unified-graph-gate-enforced-dependency-check-before-edit.md
- 2026-06-25 [claude]: Deliberation: extended the existing _touch_session_marker pattern instead of a new subsystem…
