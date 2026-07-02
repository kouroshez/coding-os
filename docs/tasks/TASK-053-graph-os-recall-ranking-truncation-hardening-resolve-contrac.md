---
id: TASK-053
title: "graph_os recall+ranking+truncation hardening: resolve contract handlers, de-pollute PageRank, honest truncation"
swimlane: core
kind: bug
epic: null
labels: []
status: archive
priority: P2
appetite: "1d"
created: 2026-06-01
started: 2026-06-01
completed: 2026-06-01
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-053: graph_os recall+ranking+truncation hardening: resolve contract handlers, de-pollute PageRank, honest truncation

**Outcome (one sentence):** Graph contract handlers (FastAPI routes + MCP tools) resolve to their real function nodes so `cos_graph_references`/`impact`/`rename` answer correctly; PageRank excludes test fixtures; envelope token-trim reports `result_truncated` honestly.

## Read First
- [graph-hallucination-cures.md](../engineering/graph-hallucination-cures.md) — references/impact recall contract
- [contracts.py](../../src/core/graph_os/extractors/contracts.py) `_emit` — handler edge target

## Repro Steps
1. `cos_graph_references` on any web route handler (e.g. `board_create`) → 0 callers.
2. `cos_graph_ranking(top=20)` → 100% `tests/` fixtures, zero production hubs.
3. `cos_graph_contracts(kinds=mcp)` → `count=78` but visible payload 70, `result_truncated=false`.

Expected: handler shows its route as caller; ranking shows production hubs; `result_truncated` truthful.
Actual (pre-fix): empty callers (81/81 route + 81/81 mcp edges → phantom stubs); test-only ranking; silent drop of 8 handlers.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a FastAPI route handler or MCP tool, **When** `cos_graph_references`/`impact` runs, **Then** the route/tool node appears as a caller (MCP 78/78, all real `.py` routes resolved).
- **Given** `cos_graph_ranking(top=20)` without `include_tests`, **When** it returns, **Then** zero `tests/` nodes in the result.
- **Given** a contracts response trimmed by the token budget, **When** returned, **Then** `meta.result_truncated=true`.
- **Given** the graph_os matrix suite, **When** run, **Then** green (712 passed).

## Work Log
- 2026-06-01 [claude]: F1: contracts.py resolves route/MCP handlers to real same-file function nodes (.py-gated) — MCP 78/78, routes 65/79 (14 
