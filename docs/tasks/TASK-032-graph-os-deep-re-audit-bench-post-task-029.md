---
id: TASK-032
title: "Graph-OS deep re-audit + bench (post-TASK-029)"
swimlane: infra
kind: spike
epic: null
labels: [graph_os, audit, exhaustive, mcp, bench]
status: in_progress
priority: P1
appetite: "1d"
created: 2026-05-25
started: 2026-05-25
completed: null
agent_session: ses-claude-20260525-044525-c0a3
depends_on: []
blocked_by: []
references: []
---
# TASK-032: Graph-OS deep re-audit + bench (post-TASK-029)

**Outcome (one sentence):** Re-verify all 14 fixes hold under reindexed graph; exercise every cos_graph_* tool with edge-case inputs; bench latency p50/p99; surface new defects; reviewer subagent PASS.

## Work Log
- 2026-05-25 [claude]: Audit pass 1 complete
- 2026-05-25 [claude]: Audit complete — 56 findings + reviewer PASS
- 2026-05-25 [claude]: Perf bench done — 63 total defects + ExhaustiveEvidence submitted
