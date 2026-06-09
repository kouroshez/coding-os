---
id: TASK-285
title: "Expand nudge-graph-os.sh to cover conceptual + missing structural queries (fix 67% miss rate)"
swimlane: core
kind: feature
epic: retrieval-routing-fix
labels: [routing, hooks, agent-confusion, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-06-09
started: 2026-06-09
completed: 2026-06-09
agent_session: ses-claude-20260609-143642-c7c5
depends_on: []
blocked_by: []
references: []
---
# TASK-285: Expand nudge-graph-os.sh to cover conceptual + missing structural queries (fix 67% miss rate)

**Outcome (one sentence):** Close the nudge gap measured at 6/9 representative queries missing. Add conceptual-question patterns ("how does X work", "explain", "what is", "overview", "understand") routing to cos_graph_context / codebase-explorer, and add patterns for the uncovered graph tools (dead_code, test_gap, cycles, centrality, ranking, diff, query, resolve, communities) so coverage rises from 13/22 tools toward full. Keep matching deterministic and fail-loud (emit recommendation to stderr; never silent). Preserve existing structural patterns and per-pattern debounce. Re-render adapter templates + golden after edit.

## Read First
- src/core/hooks/nudge-graph-os.sh
- src/core/rules/meta-graph-first.md
- src/core/hooks/registry.yaml

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the measured routing corpus (9 representative queries; 6 currently miss, 13/22 graph tools covered).
- **When** a user submits a conceptual question ("how does graph work?", "explain the sync flow", "what is graph_os?") or an uncovered-structural one ("find dead code", "test coverage gaps").
- **Then** nudge-graph-os.sh emits a graph-tool recommendation to stderr for each (cos_graph_context / codebase-explorer / cos_graph_dead_code / cos_graph_test_gap), every pre-existing structural pattern still fires, nothing is emitted silently, `make verify-hooks` is green, and adapter templates + golden fixtures are re-rendered to match.

## Work Log
- 2026-06-09 [claude]: Expanded nudge-graph-os.sh: added 9 missing structural tools (diff, query, cycles, dead_code, test_gap, centrality, rank
