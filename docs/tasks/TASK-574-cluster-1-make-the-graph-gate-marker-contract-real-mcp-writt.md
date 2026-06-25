---
id: TASK-574
title: "Cluster 1 \u2014 Make the graph-gate marker contract real: MCP-written, freshness-bound, panel-scoped + GC, with producer-side round-trip test"
swimlane: "graph_os"
kind: refactor
epic: graph-first-enforcement
labels: [graph, hooks, marker-contract, freshness, graph-gate, ready]
status: icebox
priority: P1
appetite: 1d
created: 2026-06-25
started: null
completed: null
agent_session: null
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
GIVEN a real cos_graph_context(target) call WHEN the agent then edits target THEN the enforce hook passes WITHOUT any hand-written marker (producer-side round-trip test asserts the MCP call wrote .graph/ctx-<sha>); GIVEN the file content changed since the consult THEN the marker is treated stale and the hook re-warns; GIVEN session end THEN .graph/ markers are GC'd; AND a stale graph read surfaces meta.stale=true; AND graph_os matrix suite green.

## Work Log
