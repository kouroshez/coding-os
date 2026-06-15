---
id: TASK-425
title: "Smoke test: subsystem module gating \u2014 MCP tools + hooks in/out of circuit"
swimlane: core
kind: test
epic: null
labels: [modules, testing, smoke, ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-15
started: 2026-06-15
completed: 2026-06-15
agent_session: ses-claude-20260615-014142-5969
depends_on: []
blocked_by: []
references: []
---
# TASK-425: Smoke test: subsystem module gating — MCP tools + hooks in/out of circuit

**Outcome (one sentence):** A runnable smoke test that demonstrates how subsystem modules are handled end-to-end — enabling/disabling a module puts its MCP tool family and hooks in/out of circuit. Closes the visibility gap: existing tests cover hook overrides (test_project_overrides) and state/deps (test_cli::TestSubsystems) but NOT the MCP tool gate (`_shared.py::_gated_module` returning `module_disabled`).

## Read First
- src/core/thinking_os/tools/_shared.py — _gated_module / safe_tool module_disabled gate
- src/cli/module_commands.py — module_state_payload (the per-module output shape)
- src/cli/subsystems.py — set_module_enabled, module_state, dependency engine
- src/core/subsystems.yaml — module→tools/hooks catalog
- tests/test_project_overrides.py — sibling test style (hook overrides)

## Acceptance (G/W/T) — *this IS the Definition of Done*

### 1 Output shape
- **Given** a project (no state file = all enabled)
- **When** module_state_payload(project) is read
- **Then** every module reports id/label/kernel/enabled/depends_on/hooks/tools; kernel.enabled is True; tasks.depends_on contains docs; graph reports tools > 0

### 2 Single module gated
- **Given** COS_STATE_DIR with subsystems-state.json disabling graph
- **When** _gated_module is asked about tool names
- **Then** a cos_graph_* tool is gated to "graph" while a cos_task_* tool is not gated (None)

### 3 Multi-module / graph-only
- **Given** docs + tasks + memory disabled (a graph-only project)
- **When** _gated_module is asked
- **Then** cos_doc_*, cos_task_*, and cos_search are gated to their modules while cos_graph_* runs

### 4 Agent-visible envelope
- **Given** graph disabled and a safe_tool-wrapped cos_graph_* function
- **When** it is called
- **Then** it returns a fail envelope with category "module_disabled" naming the module + `cos module enable graph` remediation

## Work Log
- 2026-06-15 [claude]: Filed after the user asked for a smoke test showing module handling. `cos module list [--format json]` already shows the per-module picture at runtime; this test pins the MCP tool gate that no existing test covered.
- 2026-06-15 [claude]: Edit test_module_gating_smoke.py
- 2026-06-15 [claude]: commit 5e939c138b — test(modules): smoke test for subsystem MCP tool gating (module_disabled + graph-only) TASK-425
- 2026-06-15 [claude]: Done (commit 5e939c13). tests/test_module_gating_smoke.py — 7 tests, all green. Covers: (1) module_state_payload shape (
- 2026-06-15 [claude]: Status transitioned to complete via cos task-done.
