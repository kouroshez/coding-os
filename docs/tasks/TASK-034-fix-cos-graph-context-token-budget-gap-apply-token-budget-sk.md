---
id: TASK-034
title: "Fix cos_graph_context token-budget gap — _apply_token_budget skips neighbours/edges_by_type"
swimlane: infra
kind: bug
epic: null
labels: [graph_os, envelope, token-budget, bug-from-prod]
status: in_progress
priority: P0
appetite: "2h"
created: 2026-05-26
started: 2026-05-26
completed: null
agent_session: ses-claude-20260526-003648-f813
depends_on: []
blocked_by: []
references: []
---
# TASK-034: Fix cos_graph_context token-budget gap — _apply_token_budget skips neighbours/edges_by_type

**Outcome (one sentence):** cos_graph_context at depth=2 on high-fan-in hub (e.g. write-state.sh, 150 callers) returns >32KB → MCP cap exceeded. G33 capped BFS visit_limit but _apply_token_budget only trims body['results'] — context uses neighbours+edges_by_type so trimmer never fires. Fix _apply_token_budget to handle multi-key trim AND/OR cos_graph_context emits minimal node fields at depth>=2.

## Read First
- docs/engineering/mcp-error-envelope.md
- docs/engineering/graph-os-deep-audit-findings-2026-05-25.md
- src/core/thinking_os/tools/_shared.py
- src/core/graph_os/tools/graph.py

## Repro Steps
1. Call `cos_graph_context(uid_or_name="code:file:src/core/hooks/write-state.sh", depth=2)`
2. File is referenced by ~150 hooks (high fan-in)
3. visit_limit=250 (G33 cap) → BFS visits 108 nodes
4. Each neighbour serialized as full NodeSummary (uid+kind+label+file_path+start_line+end_line+signature+lang) → ~250B × 108 = 27KB
5. edges_by_type adds another ~20KB
Expected: envelope <32KB OR meta.truncated=true with reduced payload
Actual: 50,771 char serialized → MCP "result exceeds maximum allowed tokens" error, tool unusable

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a high-fan-in node (write-state.sh, 150+ callers)
- **When** cos_graph_context(uid, depth=2) is invoked
- **Then** envelope ≤ TOKEN_BUDGET_CHARS (32KB), `meta.truncated=true` surfaces the cut, and downstream consumers (Hub UI / agent) get a usable response. Regression test asserts the envelope cap.

## Work Log
