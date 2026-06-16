---
id: TASK-423
title: "Graph empty-state: validate edge_type/kind vs canonical schema (not present rows) + module-aware auto-index on cos init"
swimlane: "graph_os"
kind: bug
epic: null
labels: [graph, module-aware, backward-compat, dx, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-06-15
started: 2026-06-15
completed: 2026-06-15
agent_session: ses-claude-20260615-014142-5969
depends_on: []
blocked_by: []
references: []
---
# TASK-423: Graph empty-state: validate edge_type/kind vs canonical schema (not present rows) + module-aware auto-index on cos init

**Outcome (one sentence):** A freshly-created or unindexed project's graph view returns a graceful empty result (or the graph is auto-built) instead of erroring "unknown edge_type(s) ['contains']; known: []". Edge_type/kind validation uses a canonical static set / NodeKind enum (not present DB rows), restoring the documented "empty result is valid" graph contract. cos init auto-builds the graph when the graph module is enabled, with an opt-out — no manual reindex needed.

## Read First
- src/core/graph_os/tools/graph.py
- src/cli/main.py
- src/core/graph_os/types.py
- .claude/skills/graph-os-authoring/SKILL.md
- src/core/board_os/hub_adapter_manifest.py

## Repro Steps
Create any project (e.g. cos init, even without --no-index) → open the Hub Graph tab → "unknown edge_type(s) ['contains']; known: []". Root: graph_nodes=0 because cos init never builds the graph (the --index flag is RAG-doc only), AND cos_graph_export validates 'contains' against SELECT DISTINCT edge_type FROM graph_edges_v12 (empty) at src/core/graph_os/tools/graph.py:2566-2580, so a valid core edge type is rejected.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** an empty/unindexed graph, **When** cos_graph_export(edge_types='contains') runs, **Then** it returns ok with empty edges (NOT a validation fail).
- **Given** an empty graph, **When** cos_graph_export(edge_types='not_a_real_type') runs, **Then** it still returns fail('validation', ...) — typo guard preserved.
- **Given** an empty graph, **When** cos_graph_centrality(kind='function') runs, **Then** it returns ok empty (not a hard fail on a valid kind).
- **Given** the graph module is enabled, **When** a project is created via cos init, **Then** its graph is built automatically (graph_nodes > 0) with no manual reindex.
- **Given** the graph module is disabled, **When** cos init runs, **Then** no graph build is attempted (no error, no empty-db churn).
- **Given** a populated graph, **When** any edge_types/kind filter runs, **Then** behavior is unchanged (backward-compatible).

## Work Log
- 2026-06-15 [claude]: Edit graph.py
- 2026-06-15 [claude]: Edit graph.py
- 2026-06-15 [claude]: Edit graph.py
- 2026-06-15 [claude]: Edit test_graph_empty_state.py
- 2026-06-15 [claude]: Edit test_graph_empty_state.py
- 2026-06-15 [claude]: Edit test_graph_empty_state.py
- 2026-06-15 [claude]: Edit test_graph_empty_state.py
- 2026-06-15 [claude]: Edit test_graph_empty_state.py
- 2026-06-15 [claude]: Edit test_graph_empty_state.py
- 2026-06-15 [claude]: Edit test_graph_empty_state.py
- 2026-06-15 [claude]: Edit test_graph_empty_state.py
- 2026-06-15 [claude]: commit b2f1426e1e — fix(presence): Hub chat writes its own presence so it shows in the Live-agents HUD (P13)
- 2026-06-15 [claude]: Edit main.py
- 2026-06-15 [claude]: Edit main.py
- 2026-06-15 [claude]: Edit main.py
- 2026-06-15 [claude]: Edit main.py
- 2026-06-15 [claude]: Edit main.py
- 2026-06-15 [claude]: Edit main.py
- 2026-06-15 [claude]: Edit main.py
- 2026-06-15 [claude]: Edit main.py
- 2026-06-15 [claude]: Edit main.py
- 2026-06-15 [claude]: Edit test_cli.py
- 2026-06-15 [claude]: Edit test_init_graph_index.py
- 2026-06-15 [claude]: commit fe78677322 — test(cli): cover cos init graph auto-build gating; keep cli suite fast (TASK-423)
- 2026-06-15 [claude]: Fixed two root causes. (B) graph.py: validate edge_types/kind against canonical _KNOWN_EDGE_TYPES (35) + NodeKind enum i
- 2026-06-15 [claude]: Status transitioned to complete via cos task-done.
