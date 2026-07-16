---
id: TASK-414
title: "Dependency-aware task readiness + atomic claim-next for safe autonomous multi-agent execution"
swimlane: "board_os"
kind: feature
epic: null
labels: [board_os, autonomous, dependencies, concurrency, ready]
status: archive
priority: P1
appetite: 3d
created: 2026-06-14
started: 2026-06-13
completed: 2026-06-13
agent_session: ses-claude-20260613-152557-2063
depends_on: []
blocked_by: []
references: []
---
# TASK-414: Dependency-aware task readiness + atomic claim-next for safe autonomous multi-agent execution

**Outcome (one sentence):** Task dependencies become load-bearing so autonomous multi-agent runs never stall, die on a blocked task, or execute work before its prerequisites: (A) cos_task_move blocks icebox→in_progress when any depends_on is incomplete with a RETRYABLE conflict envelope (config-gated workflow_policy.require_deps_complete, force/override escape); (B) completing a task auto-readies dependents whose deps are now ALL complete + DoR-complete (and surfaces unblocked-but-unauthored / terminal-dep-failed cases instead of hanging); (C) cos_task_pick excludes dep-incomplete icebox tasks so candidates are runnable-now only; (E) a new atomic cos_task_claim_next selects+claims the highest-priority runnable task in ONE transaction so N concurrent agents each get a DISTINCT task or {claimed:null}, never the same task twice and never an exception.

## Read First
- src/core/board_os/workflow.py
- src/core/board_os/mcp_tools.py
- src/core/board_os/transition_gates_validator.py
- src/core/board_os/transition-gates.yaml
- docs/governance/task-lifecycle.md
- docs/engineering/mcp-error-envelope.md

## Acceptance (G/W/T) — *this IS the Definition of Done*

- **(A) Dependency gate** — **Given** TASK-386 with 11 incomplete `depends_on` and the ready label, **When** `cos_task_move(TASK-386,'in_progress')` runs with `require_deps_complete` enabled, **Then** it returns `fail(category='conflict')` naming the incomplete prerequisites and does NOT transition; with `force=True` (or override env) it proceeds.
- **(B) Completion cascade** — **Given** a task whose LAST incomplete dependency transitions to complete, **When** that completion is recorded, **Then** every dependent with all-deps-complete AND a complete DoR body is auto-labeled `ready` (blocked→icebox if needed) and the action is logged/evented; a dependent that still has another open dep stays unreadied; a dependent unblocked but DoR-incomplete is surfaced as needs-authoring, not silently hidden; a dependent whose dep was archived/cancelled (terminal-failed) does not hang — it is left blocked with a reason.
- **(C) Pick filter** — **Given** `cos_task_pick` over an icebox set, **When** any candidate has an incomplete dependency, **Then** it is excluded from the returned candidates (only runnable-now tasks surface).
- **(E) Atomic claim-next** — **Given** N concurrent sessions calling `cos_task_claim_next`, **When** they race on the same runnable set, **Then** each receives a DISTINCT task moved to in_progress with its `agent_session` set atomically, or `ok({claimed:null})`; no two sessions ever claim the same task and no call raises/stalls.
- **(Verify)** — **Given** all changes, **When** the board_os + cli + thinking_os verification-matrix suites run, **Then** green, with new tests covering the dependency gate, the completion cascade, the pick filter, and the atomic claim-next race.

## Work Log
- 2026-06-14 [claude]: Edit mcp_tools.py
- 2026-06-14 [claude]: Edit test_mcp_tools.py
- 2026-06-14 [claude]: Edit stream.py
- 2026-06-14 [claude]: Edit stream.py
- 2026-06-14 [claude]: Edit useBoardStream.ts
- 2026-06-14 [claude]: Edit useBoardStream.ts
- 2026-06-14 [claude]: Edit test_stream_dedup.py
- 2026-06-14 [claude]: Edit task-lifecycle.md
- 2026-06-14 [claude]: Edit workflow.py
- 2026-06-14 [claude]: Edit workflow.py
- 2026-06-14 [claude]: Edit config.py
- 2026-06-14 [claude]: Edit config.py
- 2026-06-14 [claude]: Edit scrumban-config.yaml
- 2026-06-14 [claude]: Edit mcp_tools.py
- 2026-06-14 [claude]: Edit mcp_tools.py
- 2026-06-14 [claude]: Edit mcp_tools.py
- 2026-06-14 [claude]: Edit test_dependency_gate.py
- 2026-06-14 [claude]: Edit workflow.py
- 2026-06-14 [claude]: Edit task-lifecycle.md
- 2026-06-14 [claude]: Edit _dbg_dep_gate.py
- 2026-06-14 [claude]: Edit _dbg_dep_gate.py
- 2026-06-14 [claude]: Edit _dbg_dep_gate.py
- 2026-06-14 [claude]: Edit test_dependency_gate.py
- 2026-06-14 [claude]: Edit test_dependency_gate.py
- 2026-06-14 [claude]: Edit test_dependency_gate.py
- 2026-06-14 [claude]: Edit test_dependency_gate.py
- 2026-06-14 [claude]: Edit workflow.py
- 2026-06-14 [claude]: Edit mcp_tools.py
- 2026-06-14 [claude]: Edit mcp_tools.py
- 2026-06-14 [claude]: Edit mcp_tools.py
- 2026-06-14 [claude]: Edit mcp_tools.py
- 2026-06-14 [claude]: Edit server.py
- 2026-06-14 [claude]: Edit test_dependency_gate.py
- 2026-06-14 [claude]: Edit test_dependency_gate.py
- 2026-06-14 [claude]: Edit test_dependency_gate.py
- 2026-06-14 [claude]: Edit test_dependency_gate.py
- 2026-06-14 [claude]: Edit mcp-tool-inventory.md
- 2026-06-14 [claude]: Edit task-lifecycle.md
- 2026-06-14 [claude]: Implemented (B) completion cascade: cascade_ready_dependents in mcp_tools.py + dependents_of in workflow.py; wired into
- 2026-06-14 [claude]: Implemented (E) atomic cos_task_claim_next (mcp_tools.py + server.py registration): reuses cos_task_pick then atomic CAS
- 2026-06-14 [claude]: Tests: 7 new in test_dependency_gate.py (3 cascade incl. multi-dep/needs-authoring, 4 claim-next incl. concurrent race).
- 2026-06-14 [claude]: Edit test_dependency_gate.py
- 2026-06-14 [claude]: A/B/C/E done: dep-gate(transient)+pick-filter+cascade+cos_task_claim_next; board_os 501/cli 148/thinking_os 1412 green;
- 2026-06-14 [claude]: committed 1ca8e4d5: docs/governance/mcp-tool-inventory.md, docs/governance/task-lifecycle.md, src/core/board_os/config.p
