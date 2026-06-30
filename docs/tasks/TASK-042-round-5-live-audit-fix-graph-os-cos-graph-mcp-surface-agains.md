---
id: TASK-042
title: "Round-5 LIVE audit + fix: graph_os & cos_graph_* MCP surface against live server"
swimlane: infra
kind: chore
epic: null
labels: []
status: archive
priority: P2
appetite: "1d"
created: 2026-05-29
started: 2026-05-29
completed: 2026-05-29
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-042: Round-5 LIVE audit + fix: graph_os & cos_graph_* MCP surface against live server

**Outcome (one sentence):** Independently re-derive ground truth and validate every cos_graph_* tool against the freshly-restarted LIVE server; confirm F1-F9 fixes hold live; audit tool-list for over-engineering/duplication; fix any real bug found and verify.

## Work Log
- 2026-05-29 [claude]: Round-5 LIVE audit complete: 33-agent fleet, 25/26 findings reproduced. Coverage clean (1074/1075, 0 phantom). Caller-re
