---
id: TASK-573
title: "ADR + design lock: unified graph-gate (MCP-written freshness markers, data-driven scope, centrality-graded severity, cross-adapter parity, consumer migration)"
swimlane: core
kind: docs
epic: graph-first-enforcement
labels: [governance, graph, adr, graph-gate, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-06-25
started: 2026-06-25
completed: 2026-06-25
agent_session: ses-claude-20260625-122147-96fb
depends_on: []
blocked_by: []
references: []
---
# TASK-573: ADR + design lock: unified graph-gate (MCP-written freshness markers, data-driven scope, centrality-graded severity, cross-adapter parity, consumer migration)

**Outcome (one sentence):** A locked ADR under docs/architecture/adr/ specifying the consolidated graph-gate: (1) marker contract written by the MCP tools themselves, freshness-bound via content_hash + index epoch, in one $COS_PANEL_DIR/.graph/ namespace with GC; (2) data-driven meta-vs-consumer scope rendered from stack.yaml (delete the bash hardcode + _in_meta_source_tree); (3) centrality-graded severity from a reindex-time cache (never synchronous MCP in the hot path); (4) cross-adapter parity via a Bash-mediated delegate + dispatcher preamble; (5) SM6 backward-compat consumer migration plan (golden regen, old-marker sweep, parity test). Clusters 1-6 implement against this fixed contract.

## Read First
- docs/governance/critical-rules.md
- src/templates/meta/rules/graph-first.md
- src/core/hooks/registry.yaml
- docs/engineering/graph-hallucination-cures.md

## Work Log
- 2026-06-25 [claude]: Edit 0014-unified-graph-gate-enforced-dependency-check-before-edit.md
- 2026-06-25 [claude]: Wrote ADR-0014 (unified graph-gate): marker contract MCP-written + freshness + GC, one event-keyed hook, data-driven…
- 2026-06-25 [claude]: committed eb47932c · 2 files
- 2026-06-25 [claude]: committed 8f326786 · 8 files
- 2026-06-25 [claude]: committed 50bca959 · 28 files
- 2026-06-25 [claude]: committed 742d9efb · 6 files
- 2026-06-25 [claude]: committed 1eb80414 · 39 files
