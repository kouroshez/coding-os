---
id: TASK-402
title: "Graph tab spine UX + export truncation transparency + walk-tool coverage audit"
swimlane: "graph_os"
kind: bug
epic: null
labels: [graph-os, hub-ui, ux, audit, ready]
status: archive
priority: P1
appetite: 1d
created: 2026-06-11
started: 2026-06-11
completed: 2026-06-11
agent_session: ses-claude-20260611-120804-a06f
depends_on: []
blocked_by: []
references: []
---
# TASK-402: Graph tab spine UX + export truncation transparency + walk-tool coverage audit

**Outcome (one sentence):** Graph tab is unambiguous and complete: initial view explains itself (or defaults to the repo-root spine), depth=max with a node budget visibly reports what was cut (truncation badge with counts) instead of silently dropping task subtrees, the contains-spine logic is verified end-to-end (extractor → DB → export API → Sigma render), graph walk tools (references/impact on init_db) are proven complete against grep ground truth with honest truncation flags, and agent guidance (graph-explorer skill, playbooks, hooks, CLAUDE.md) matches the audited behavior.

## Read First
- src/core/web/ui/src/features/graph
- src/core/web/routes/graph.py
- src/core/graph_os/tools/graph.py
- src/core/graph_os/tests/test_smart_export.py
- src/core/skills/graph-explorer/SKILL.md

## Repro Steps
1. Open Hub → Graph with no spine selection: an "Auto" multi-cluster scatter renders with no explanation of what is shown or what was omitted (2026-06-11 screenshots).
2. Select repo-root in the CONTAINS SPINE sidebar: view switches to the rooted BFS — relationship between the two states is not communicated.
3. Set depth to ALL/MAX and zoom into docs/tasks: task nodes render partially; no badge says the node budget (low/med/high/max) cut the subtree.
Expected: rooted-vs-auto semantics are explicit, every cut is surfaced with counts. Actual: silent truncation reads as a broken/missing graph.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the Graph tab on first open, **When** no root is selected, **Then** the UI states what view is shown (auto-sampled overview) and how to get the full spine, OR defaults to the repo-root spine.
- **Given** any rooted view whose BFS hit the node/hop budget, **When** it renders, **Then** a visible badge reports nodes shown/total and the budget that cut it.
- **Given** the contains-spine pipeline, **When** audited extractor → DB → /api/graph export → UI render, **Then** each hop is verified and any defect found is fixed with a test.
- **Given** cos_graph_references/impact on init_db, **When** compared against grep ground truth, **Then** results are complete (or honestly flagged truncated) and the probe→widen workflow documented in graph-explorer matches reality.
- **Given** the agent-guidance surfaces (skill, playbooks, hooks, CLAUDE.md), **When** audited, **Then** their claims match the verified behavior.

## Work Log
- 2026-06-11 [claude]: Edit graph.py
- 2026-06-11 [claude]: Edit graph.py
- 2026-06-11 [claude]: Edit graph-adapter.ts
- 2026-06-11 [claude]: Edit GraphCanvas.tsx
- 2026-06-11 [claude]: Edit sqlite_backend.py
- 2026-06-11 [claude]: Edit graph_commands.py
- 2026-06-11 [claude]: Edit reindex_dispatch.py
- 2026-06-11 [claude]: Edit SKILL.md
- 2026-06-11 [claude]: Edit SKILL.md
- 2026-06-11 [claude]: Edit polyglot-extractor-roadmap.md
- 2026-06-11 [claude]: Edit hooks.ts
- 2026-06-11 [claude]: Edit hooks.ts
- 2026-06-11 [claude]: Edit GraphCanvas.tsx
- 2026-06-11 [claude]: Edit graph.py
- 2026-06-11 [claude]: Edit ContainsTree.tsx
- 2026-06-11 [claude]: Root causes found+fixed: (1) server silently clamped export max_nodes to 2000 — UI's 10k/30k asks (depth=max, spine side
- 2026-06-11 [claude]: Status transitioned to complete via cos task-done.
- 2026-06-11 [claude]: committed e6c434cb: docs/playbooks/polyglot-extractor-roadmap.md, src/cli/graph_commands.py, src/core/graph_os/backends/
