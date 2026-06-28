---
id: TASK-639
title: "Dispatch safety: per-chain budget ceiling, EvidenceBundle write-lock, DispatchRequest max_turns hop-cap"
swimlane: core
kind: feature
epic: multi-model-autonomy
labels: [dispatch, budget, concurrency, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-06-28
started: 2026-06-28
completed: 2026-06-28
agent_session: ses-claude-20260627-204916-f0ee
depends_on: []
blocked_by: []
references: []
---
# TASK-639: Dispatch safety: per-chain budget ceiling, EvidenceBundle write-lock, DispatchRequest max_turns hop-cap

**Outcome (one sentence):** Make real sub-agent dispatch safe to activate by adding the two prerequisites the dispatch-deferral ADR named, plus a recursion guard: a per-chain USD ceiling (COS_CHAIN_BUDGET_USD) summing formula_dispatches by task_marker, an fcntl.flock write-lock around EvidenceBundle writes for concurrency-safe parallel runs, and a DispatchRequest.max_turns hop-cap to defang runaway recursive delegation.

## Read First
- src/core/thinking_os/tools/cognition.py
- src/core/thinking_os/budget.py
- src/adapters/claude/sdk_dispatcher.py
- docs/governance/adr-role-dispatch-deferral.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a chain whose summed cost_usd >= COS_CHAIN_BUDGET_USD, **When** another dispatch is requested, **Then** it returns fail('budget',...) before spawn (fail-closed-open on misconfig, mirroring budget.check).
- **Given** two concurrent EvidenceBundle writes, **When** they race, **Then** the flock serializes them with no lost update.
- **Given** DispatchRequest.max_turns=N, **When** dispatched, **Then** the SDK honors N; the explicit>default precedence is documented in the dataclass docstring.
- **Given** the adapters and thinking_os suites, **When** run, **Then** green.

## Work Log
- 2026-06-28 [claude]: Edit dispatcher.py
- 2026-06-28 [claude]: Edit budget.py
- 2026-06-28 [claude]: Edit budget.py
- 2026-06-28 [claude]: Edit cognition.py
- 2026-06-28 [claude]: Edit cognition.py
- 2026-06-28 [claude]: Edit sdk_dispatcher.py
- 2026-06-28 [claude]: Edit test_dispatch_safety.py
- 2026-06-28 [claude]: Edit commit639.txt
- 2026-06-28 [claude]: Shipped the 2 dispatch-deferral-ADR prerequisites + a recursion guard. budget.py: chain_check(db, task_marker) sums…
- 2026-06-28 [claude]: Status transitioned to complete via cos task-done.
