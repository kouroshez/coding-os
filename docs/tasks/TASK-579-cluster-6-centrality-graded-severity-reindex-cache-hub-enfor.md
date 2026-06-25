---
id: TASK-579
title: "Cluster 6 \u2014 Centrality-graded severity (reindex cache) + Hub enforcement config + propose-not-apply self-tuning + i18n harakat index-fold + export-XSS render-boundary guard"
swimlane: core
kind: feature
epic: graph-first-enforcement
labels: [severity, hub, learning, i18n, xss, graph-gate, ready]
status: icebox
priority: P3
appetite: 1d
created: 2026-06-25
started: null
completed: null
agent_session: null
depends_on: [TASK-573, TASK-574, TASK-576]
blocked_by: []
references: []
---

# TASK-579: Cluster 6 — Centrality-graded severity (reindex cache) + Hub enforcement config + propose-not-apply self-tuning + i18n harakat index-fold + export-XSS render-boundary guard

**Outcome (one sentence):** graph-gate grades severity by fan-in read from a reindex-time precomputed cache (high-centrality node blocks-by-default, leaf warns) — never a synchronous cos_graph_* call in the Write/Edit hot path, with a micro-bench latency ceiling locking the invariant; the Hub gains a graph-enforcement settings section (view/flip warn|strict|off + enforce_context_on) mirroring the git_settings->cos-env.sh write path; an opt-in propose-not-apply review queue surfaces high-centrality nodes for human-approved guarding (never auto-mutate config); the FTS index is harakat-folded so Persian/Arabic symbols are findable (TASK-485) with a round-trip test; export labels are escaped at the render boundary with an adversarial test + a CI grep-guard against an HTML sink (TASK-486); the enforce-skill test-file dead zone is scoped so high-fan-in test helpers are not a blind spot. Closes D1, D4, N7, N8, N9, SM4, SM5, B6.

## Read First
- src/core/graph_os/tools/graph.py
- src/core/web/routes/settings.py
- src/core/web/ui/src/pages/ConfigPage.tsx
- src/core/graph_os/database.py
- src/core/thinking_os/tools/learning.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** an edit to a 162-dependent node **When** graph-gate runs **Then** it blocks-by-default reading a local centrality cache (no MCP round-trip, micro-bench under ceiling); **Given** the Hub Config page **When** an operator opens it **Then** graph enforcement is viewable and flippable; **Given** harakat-bearing indexed text **When** searched **Then** it is found (round-trip test); **Given** a malicious node label **When** export renders **Then** it is escaped at the boundary and CI fails if output reaches an HTML sink; AND graph_os + web + hooks matrix suites green.

## Work Log
