---
id: TASK-817
title: "MCP surface honesty \u2014 merge/disjoin graph_query vs graph_search + explicit kernel always-on tool floor (rank 11)"
swimlane: core
kind: refactor
epic: modularity-completion
labels: [ready]
status: complete
priority: P3
appetite: 1d
created: 2026-07-16
started: 2026-07-16
completed: 2026-07-16
agent_session: ses-claude-20260716-001729-7bd4
depends_on: []
blocked_by: []
references: []
---
# TASK-817: MCP surface honesty — merge/disjoin graph_query vs graph_search + explicit kernel always-on tool floor (rank 11)

**Outcome (one sentence):** The MCP tool surface is smaller and the SSOT is honest: the overlapping cos_graph_query/cos_graph_search confusion is resolved, and the four un-gateable always-on tools (classify_prompt/health/traceability/failure_pattern_query) are either declared as kernel.tools (auditable floor) or moved into their true owning module so disabling it removes them.

## Read First
- src/core/thinking_os/server.py
- src/core/subsystems.yaml
- src/core/thinking_os/tools/_shared.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** cos_graph_query and cos_graph_search overlap on free-text symbol search and 4 tools match no module while kernel declares tools:[], **When** this lands, **Then** the two graph tools are merged (rank=/expand= options) or their docstrings are sharply disjoined, and the always-on floor is explicit — kernel.tools lists them OR cos_traceability/cos_failure_pattern_query move to tasks/observability so disabling that module removes them.
Checklist:
- [ ] Decide merge vs disjoin for graph_query/search (verify backends: lexical+expansion vs semantic+centrality) — reuse-first, avoid breaking callers.
- [ ] Make kernel.tools honest: list the intended always-on tools, or reassign cos_traceability (tasks) + cos_failure_pattern_query (cognition/observability — it reads backtrack_events).
- [ ] Update docs/governance/mcp-tool-inventory.md count if it drifted.
- [ ] Tests: gating removes the reassigned tools when their module is off; graph tool change keeps callers green.
- [ ] Verify: uv run --extra rag pytest src/core/thinking_os/tests/ -q -m 'not slow' + python src/core/thinking_os/server.py --test.

## Work Log
- 2026-07-16 [claude]: Edit server.py
- 2026-07-16 [claude]: Edit server.py
- 2026-07-16 [claude]: Edit server.py
- 2026-07-16 [claude]: Edit server.py
- 2026-07-16 [claude]: Edit subsystems.yaml
- 2026-07-16 [claude]: Disjoined the two overlapping graph search tools (the user's 'agent hallucinates' concern): cos_graph_query…
- 2026-07-16 [claude]: commit 0d12e762a0 — refactor(core): disjoin graph_query/graph_search + honest kernel always-on tool floor
