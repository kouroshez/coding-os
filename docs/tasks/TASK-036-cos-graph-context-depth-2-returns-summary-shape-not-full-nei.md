---
id: TASK-036
title: "cos_graph_context depth>=2 returns SUMMARY shape (not full neighbours)"
swimlane: infra
kind: feature
epic: null
labels: [graph_os, envelope, agent-cost, enterprise]
status: complete
priority: P0
appetite: "2h"
created: 2026-05-26
started: 2026-05-26
completed: 2026-05-26
agent_session: ses-claude-20260526-003648-f813
depends_on: []
blocked_by: []
references: []
---
# TASK-036: cos_graph_context depth>=2 returns SUMMARY shape (not full neighbours)

**Outcome (one sentence):** cos_graph_context at depth>=2 returns counts + top-5 sample per edge_type instead of full neighbours dump. Graph layer must be CHEAPER than file reads; pre-fix depth=2 on a 150-caller hub returned 50KB defeating the entire point of the graph. Post-fix: ~2-4KB summary with drill_hint pointing agent to cos_graph_references for specifics.

## Read First
- src/core/graph_os/tools/graph.py
- src/core/web/ui/src/features/graph/ContextPanel.tsx
- src/core/skills/graph-explorer/SKILL.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a high-fan-in node (write-state.sh, ~150 callers)
- **When** cos_graph_context(uid, depth=2 or 3) is called
- **Then** response has `summary_mode=true` with `edge_counts` + `top_edges_by_type` (no full `neighbours`), envelope ≤ 6KB, `drill_hint` points caller to cos_graph_references for full lists. UI path (depth=1) shape unchanged.

## Work Log
- 2026-05-26 [claude]: summary shape landed + bench verified
