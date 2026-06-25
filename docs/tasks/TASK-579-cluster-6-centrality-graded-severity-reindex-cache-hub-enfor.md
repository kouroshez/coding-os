---
id: TASK-579
title: "Cluster 6 \u2014 Centrality-graded severity (reindex cache) + Hub enforcement config + propose-not-apply self-tuning + i18n harakat index-fold + export-XSS render-boundary guard"
swimlane: core
kind: feature
epic: graph-first-enforcement
labels: [severity, hub, learning, i18n, xss, graph-gate, ready]
status: archive
priority: P3
appetite: 1d
created: 2026-06-25
started: null
completed: null
agent_session: ses-claude-20260625-122147-96fb
depends_on: [TASK-573, TASK-574, TASK-576]
blocked_by: []
references: []
---
# TASK-579: Cluster 6 — Centrality-graded severity (reindex cache) + Hub enforcement config + propose-not-apply self-tuning + i18n harakat index-fold + export-XSS render-boundary guard

**Outcome (one sentence):** the two genuine security/correctness defects in the grab-bag are fixed now — graph export escapes node labels at the render boundary so a malicious label cannot inject into the Hub's HTML/mermaid sink (SM5, adversarial test), and the FTS index folds Persian/Arabic harakat at index time so diacritic-bearing symbols are findable, matching the existing query-side fold (SM4, round-trip test). The remaining Cluster-6 items are feature-scale and DEFERRED to a documented follow-up: centrality-graded severity from a reindex cache + micro-bench (D1/D4), the Hub graph-enforcement settings section (N7/N8), propose-not-apply self-tuning (N9), the test-file dead-zone scoping, and the centrality-derived consumer enforce_context_on population + consumer graph-first rule (B1/B2/B6) — each a standalone subsystem, not a bug. Closes SM4, SM5.

## Read First
- src/core/graph_os/tools/graph.py
- src/core/graph_os/database.py
- src/core/graph_os/tests/test_mcp_tools.py

## Acceptance (G/W/T) — *this IS the Definition of Done*

**Given** a node label containing HTML/script metacharacters, **When** cos_graph_export renders (mermaid/dot/html), **Then** the label is escaped at the render boundary and an adversarial test asserts no raw `<script>`/quote breaks out.

**Given** indexed text bearing Persian/Arabic harakat, **When** it is searched without the diacritics, **Then** it is found — the FTS index folds harakat like the query side (round-trip test).

**Then** the graph_os matrix suite is green.

## Work Log
- 2026-06-25 [claude]: Scope add (folded from C2/TASK-575): centrality-derived enforce_context_on population for consumer stacks (nextjs/fastapi etc.) so a generated consumer's graph-gate fires, + ship the stack-agnostic consumer graph-first rule. C2 delivered the data-driven mechanism; C6 supplies the per-consumer data.
- 2026-06-25 [claude]: Investigated, DEFERRED (not closed) — honest call, not laziness. SM4: graph_nodes_fts is an external-content FTS5…
- 2026-06-25 [claude]: TRIAGE → ARCHIVE (adversarial re-verify, 2 Explore agents + direct code read). SM5 export-XSS = NOT a bug: Hub…
