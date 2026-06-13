---
id: TASK-410
title: "Graph indexes render dirs (.claude/.codex/.cursor) \u2192 broken relative-link stubs trip uid_consistency FAIL"
swimlane: "graph_os"
kind: bug
epic: null
labels: [graph-os, doctor, extractors, ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-13
started: 2026-06-13
completed: 2026-06-13
agent_session: ses-claude-20260611-002926-83d4
depends_on: []
blocked_by: []
references: []
---
# TASK-410: Graph indexes render dirs (.claude/.codex/.cursor) → broken relative-link stubs trip uid_consistency FAIL

**Outcome (one sentence):** The graph no longer indexes adapter render-artifact dirs (.claude/.codex/.cursor) — those are derived phenotype copies of canonical src/ sources, and their copied-in relative markdown links resolve from the wrong depth, minting stale file stubs like code:file:core/hooks/registry.yaml (missing src/) that trip graph.uid_consistency. After the fix: render dirs are excluded from the walk, the md_links existence-gate also drops stubs for non-existent LOCAL targets of any extension (not just .md), the orphan node is pruned, and cos doctor graph.uid_consistency is PASS — with zero legitimate stubs or src/ doc nodes lost.

## Read First
- (no doc yet — exploratory)

## Repro Steps
1. cos graph-reindex --force (walks .claude/ render copies).
2. cos doctor.
Expected: graph.uid_consistency PASS.
Actual: FAIL — 1 node code:file:core/hooks/registry.yaml (md_links stub, stub:true) created from doc:file:.claude/rules/meta-hook-author.md whose link ../../../core/hooks/registry.yaml resolves one level short because the file is a COPY at .claude/rules/ not the src/templates/meta/rules/ original.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the meta-repo where adapter install copies rule docs into .claude/rules/ with relative links authored for the src/ source depth\n- **When** cos graph-reindex --force runs and cos doctor is evaluated\n- **Then** .claude/.codex/.cursor are excluded from the graph file-walk (verified: 0 doc:file:.claude/% nodes; the canonical src/ equivalents remain indexed), the md_links extractor drops file stubs whose local target does not exist on disk, the orphan code:file:core/hooks/registry.yaml is gone, graph.uid_consistency is PASS, and graph_os extractor + reindex tests stay green with no drop in legitimate node/edge counts.

## Work Log
- 2026-06-13 [claude]: Edit reindex_dispatch.py
- 2026-06-13 [claude]: Edit md_links.py
- 2026-06-13 [claude]: Edit test_md_links.py
- 2026-06-13 [claude]: Edit test_reindex_dispatch.py
- 2026-06-13 [claude]: Edit test_md_links.py
- 2026-06-13 [claude]: Edit polyglot-extractor-roadmap.md
- 2026-06-13 [claude]: Edit test_i7_extractors.py
- 2026-06-13 [claude]: commit 3dc5c9be3f — fix(test): Go package node asserts canonical module kind (TASK-409 follow-up)
- 2026-06-13 [claude]: committed 2c3c1fc0: docs/playbooks/polyglot-extractor-roadmap.md, src/core/graph_os/extractors/md_links.py, src/core/gra
- 2026-06-13 [claude]: Root-caused via 3-agent workflow: the FAIL was NOT the bulk walker (already excludes .claude via DEFAULT_EXCLUDE) but th
