---
id: TASK-1088
title: "Core: remove the cognition layer except supervision (role chain, situations, trajectory, metrics, learning, backtrack, ambiguity, takeover)"
swimlane: core
kind: refactor
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-10-25
started: 2026-10-25
completed: 2026-10-25
agent_session: ses-claude-20261024-131905-031f
depends_on: []
blocked_by: []
references: []
---
# TASK-1088: Core: remove the cognition layer except supervision (role chain, situations, trajectory, metrics, learning, backtrack, ambiguity, takeover)

**Outcome (one sentence):** coding-os keeps tasks, graph, docs, file memory and multi-model supervision, and drops the parts of the cognition layer that 3 months of transcripts show nobody calls, with their hooks, rules, tools and tests.

## Read First
- docs/governance/critical-rules.md
- docs/engineering/agent-supervision.md
- src/core/hooks/registry.yaml

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the operator decision (2026-10-25): remove all of the cognition layer except supervision
- **When** each removed tool, hook, rule and test is first proven unreferenced by the kept surface (tasks, graph, docs, memory, supervision dispatch)
- **Then** the removed surface is gone from code, registry, adapter templates, rules, docs and tests; the kept surface's matrix suites pass; a real supervision dispatch still runs; and MCP `--test` lists only kept tools

## Work Log
- 2026-10-25 [claude]: Step 1 (dispatch decoupling, -305 lines) and step 2a (13 tools:…
- 2026-10-25 [claude]: Done in a clean clone, ff-merged into main with the other session's registry/settings WIP saved as a patch and…
- 2026-10-25 [claude]: Status transitioned to complete via cos task-done.
