---
id: TASK-461
title: "CI guards: graph-doctor health gate + stack-count drift lint"
swimlane: infra
kind: feature
epic: audit-remediation-2026-06
labels: [audit-remediation, ready]
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

# TASK-461: CI guards: graph-doctor health gate + stack-count drift lint

**Outcome (one sentence):** The two highest-trust surfaces can no longer silently rot: (1) CI runs cos_graph_doctor and fails on healthy:false (the graph the meta-graph-first rule mandates agents trust just went unhealthy with 70 phantom nodes undetected); (2) a docs-lint check fails if any AGENTS.md/rule file hardcodes a stack count that mismatches ls src/templates. Decide CI cost first: graph gate needs the graph built in CI (reindex) — weigh cost vs a lighter 'phantom-node count' assertion. From strategic-audit (A2/A1 durable-guard half), descoped from TASK-459.

## Read First
- .github/workflows/ci.yml
- src/core/scripts/docs-lint.sh
- Makefile
- docs/engineering/graph-hallucination-cures.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
Given a PR that leaves the graph healthy:false, When CI runs, Then it fails with the doctor issue list.
Given a doc that hardcodes a wrong 'N stacks' count, When docs-lint runs, Then it fails citing the file:line and the real count.
Given the graph-build cost in CI is non-trivial, Then the chosen approach is documented (full reindex vs lightweight phantom check) with its runtime.

## Work Log
