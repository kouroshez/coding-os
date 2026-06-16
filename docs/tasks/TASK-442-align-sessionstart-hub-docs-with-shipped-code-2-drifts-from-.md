---
id: TASK-442
title: "Align SessionStart + Hub docs with shipped code (2 drifts from doc-code alignment audit)"
swimlane: core
kind: chore
epic: null
labels: [docs-update, governance, doc-code-alignment, ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-16
started: 2026-06-16
completed: 2026-06-16
agent_session: ses-803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-442: Align SessionStart + Hub docs with shipped code (2 drifts from doc-code alignment audit)

**Outcome (one sentence):** transparency-banner.md §SessionStart 'Hidden' bullet enumerates all six SS_HIDDEN blocks (adds the three startup/resume-only enrichment blocks: Project Trajectory, Autonomous Routing Evolution, token-economics) and hub-architecture.md's --graph-index 'never an empty canvas' promise carries the graph-module-disabled caveat — both docs match the shipped code.</outcome>
<parameter name="acceptance">Given session-context.sh appends six blocks to SS_HIDDEN (lines 247/298/322/333/342/350), When the transparency-banner.md §SessionStart 'Hidden (agent context)' bullet is read, Then it enumerates recovery rules + [Session State] + [MCP Prime] + [Agent Digest] + the three startup/resume-only enrichment blocks (Project Trajectory, Autonomous Routing Evolution, token-economics).
Given main.py::_initial_graph_index early-returns when the graph module is disabled (main.py:2042-2044), When hub-architecture.md's POST /api/hub/registry/init --graph-index passage is read, Then the 'never an empty canvas' promise carries the module-disabled caveat (skipped build, empty Graph tab until cos graph-reindex).
Given both edits land, When make docs-lint runs, Then it passes (link-audit hard gate green).

## Work Log
- 2026-06-16 [claude]: Edit transparency-banner.md
- 2026-06-16 [claude]: Edit hub-architecture.md
- 2026-06-16 [claude]: Fixed both drifts: transparency-banner.md §SessionStart bullet now enumerates all 6 SS_HIDDEN blocks (added the 3 startu
- 2026-06-16 [claude]: committed 99b2e759 · 2 files
