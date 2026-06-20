---
id: TASK-488
title: "Expose the 7 MCP-only graph tools over HTTP for Hub parity (search, centrality, cycles, dead_code, diff, ranking, resolve)"
swimlane: core
kind: feature
epic: null
labels: [hub, http-parity, deferred, ready]
status: icebox
priority: P2
appetite: 1d
created: 2026-06-20
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-488: Expose the 7 MCP-only graph tools over HTTP for Hub parity (search, centrality, cycles, dead_code, diff, ranking, resolve)

**Outcome (one sentence):** The 7 graph tools currently reachable only over MCP — search, centrality, cycles, dead_code, diff, ranking, resolve — become reachable from the Hub HTTP layer at parity with the existing 14, so web-panel users (and the future PR-diff view) can use the full graph surface instead of 14/21.

## Read First
- src/core/web/routes/graph.py
- src/core/web/_deps.py
- src/core/graph_os/tools/graph.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** 14 of 21 graph tools are exposed in routes/graph.py with an established typed-Query + rate-limit + envelope + per-project-scope pattern, **When** the 7 missing tools are added, **Then** each gets a GET route following that exact existing pattern (no new pattern invented, reuse _deps.py). **And** each route's response field names are verified against the producing cos_graph_* tool per api-contract discipline, not assumed. **And** a test asserts each new route's envelope shape against the producer. **And** per-project scoping and rate-limiting apply uniformly across all 7.

## Work Log
