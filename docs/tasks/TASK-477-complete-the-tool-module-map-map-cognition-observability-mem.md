---
id: TASK-477
title: "Complete the tool\u2192module map \u2014 map cognition/observability/memory tools so toggling sheds them (TASK-476 follow-up)"
swimlane: infra
kind: feature
epic: null
labels: [modularity, mcp, audit-pass4, ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-20
started: 2026-06-20
completed: 2026-06-20
agent_session: ses-claude-20260620-015545-0bbe
depends_on: [TASK-476]
blocked_by: []
references: []
---
# TASK-477: Complete the tool→module map — map cognition/observability/memory tools so toggling sheds them (TASK-476 follow-up)

**Outcome (one sentence):** subsystems.yaml's `cognition` and `observability` modules (today `tools: []` — toggleable but shed nothing, a half-wired state) gain their conceptually-owned MCP tools, and `memory` gains its retrieval/promote/digest tools. Combined with TASK-476's startup remove_tool, disabling cognition sheds ~15 tools (compose/dispatch/supervise/route/situation/role/takeover/analyze/ambiguity/backtrack/discovery) and observability sheds ~9 (metric_*/log_query/trajectory_*/presence). Surface-only change (gating never touches internal Python call paths, so task-done outcome recording etc. are unaffected). cos_classify_prompt (Record Gate, core loop) and cos_health (diagnostic) stay kernel by deliberate decision. Ambiguous-ownership tools (cos_traceability, cos_failure_pattern_query) stay kernel rather than be force-mapped (Rule 22).</outcome>

## Read First
- src/core/subsystems.yaml
- src/core/thinking_os/tests/test_module_gate_registry.py
- src/core/thinking_os/tools/_shared.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** subsystems.yaml after this change **When** the tool→module map is built (`_tool_module_map`) **Then** cognition owns the dispatch/supervise/route/compose/role/situation/takeover/analyze/ambiguity/backtrack/discovery tools and observability owns metric_*/log_query/trajectory_*/presence_query — and the existing test_module_gate_registry invariant (every mapped pattern matches ≥1 registered tool, no kernel/safety overlap) still passes.
**Given** `cognition` disabled **When** `apply_module_tool_gating(mcp)` runs on the real server **Then** cos_compose_chain + cos_dispatch_* + cos_route_* vanish from list_tools while cos_classify_prompt and cos_health survive.
**Given** no modules disabled **When** the server boots **Then** the served surface is unchanged from today (zero regression).

## Work Log
- 2026-06-20 [claude]: Edit subsystems.yaml
- 2026-06-20 [claude]: Edit subsystems.yaml
- 2026-06-20 [claude]: Edit subsystems.yaml
- 2026-06-20 [claude]: Edit test_module_gating.py
- 2026-06-20 [claude]: Edit test_module_gating.py
- 2026-06-20 [claude]: Edit modularity-audit-2026-06.md
- 2026-06-20 [claude]: Mapped cognition…
- 2026-06-20 [claude]: commit 304def375f — feat(modularity): map cognition/observability/memory MCP tools so module toggle sheds them
- 2026-06-20 [claude]: Status transitioned to complete via cos task-done.
