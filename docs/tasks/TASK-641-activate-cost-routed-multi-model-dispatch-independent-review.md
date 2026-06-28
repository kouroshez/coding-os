---
id: TASK-641
title: "Activate cost-routed multi-model dispatch: independent reviewer at a cheaper tier + cross-adapter routing"
swimlane: core
kind: feature
epic: multi-model-autonomy
labels: [dispatch, multi-model, codex, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-06-28
started: 2026-06-28
completed: 2026-06-28
agent_session: ses-claude-20260627-204916-f0ee
depends_on: [TASK-638, TASK-639]
blocked_by: []
references: []
---
# TASK-641: Activate cost-routed multi-model dispatch: independent reviewer at a cheaper tier + cross-adapter routing

**Outcome (one sentence):** Wire the first real opt-in dispatch caller — an independent reviewer sub-agent dispatched at a cheaper tier than the generator for exhaustive-audit tasks — and let cos_route_model emit an adapter hint (e.g. Codex) for mechanical/low-complexity buckets, so the agent routes sub-tasks to cheaper models/runtimes mid-run. Real cost lands in formula_dispatches via the SDK's reported total_cost_usd.

## Read First
- src/core/thinking_os/tools/cognition.py
- src/adapters/claude/sdk_dispatcher.py
- src/adapters/codex/sdk_dispatcher.py
- docs/governance/adr-role-dispatch-deferral.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** an exhaustive-audit task, **When** dispatched, **Then** an independent reviewer runs at the routed cheaper tier and a formula_dispatches row records model + real cost_usd.
- **Given** a low-complexity/mechanical bucket, **When** routed, **Then** cos_route_model returns an adapter hint and DispatchRequest.adapter routes it (both dispatchers already forward model).
- **Given** Codex (no per-call USD), **When** dispatched, **Then** cost_usd=NULL with a warning; status still feeds routing.
- **Given** the adapters and thinking_os suites plus an e2e dispatch smoke, **When** run, **Then** green and the dispatch-deferral ADR is updated to 'partially revived'.

## Work Log
- 2026-06-28 [claude]: Edit routing.py
- 2026-06-28 [claude]: Edit cognition.py
- 2026-06-28 [claude]: Edit cognition.py
- 2026-06-28 [claude]: Edit cognition.py
- 2026-06-28 [claude]: Edit cognition.py
- 2026-06-28 [claude]: Edit test_routing.py
- 2026-06-28 [claude]: Edit test_routing.py
- 2026-06-28 [claude]: Edit test_dispatch_safety.py
- 2026-06-28 [claude]: Edit commit641.txt
- 2026-06-28 [claude]: Edit commit641.txt
- 2026-06-28 [claude]: Activated cost-routed multi-model dispatch as minimal flag-gated infrastructure (no always-on sub-agent spawns, no…
- 2026-06-28 [claude]: Status transitioned to complete via cos task-done.
