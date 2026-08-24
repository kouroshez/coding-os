---
id: TASK-853
title: "Forward-cost estimate at the parallel dispatch budget gate (N-way fan-out can overrun the cap)"
swimlane: core
kind: bug
epic: null
labels: [budget, dispatch, safety, ready]
status: archive
priority: P2
appetite: 1d
created: 2026-07-24
started: 2026-07-24
completed: 2026-07-24
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-853: Forward-cost estimate at the parallel dispatch budget gate (N-way fan-out can overrun the cap)


**Outcome (one sentence):** `cos_dispatch_parallel_run` authorizes N concurrent sub-agents from a single spent-only budget check, so the daily/chain cap can be overrun by up to N x one dispatch — populate the already-plumbed `additional_estimate_usd` with a median-recent-cost x N forward estimate so the breaker stops the fan-out before it spawns.

## Read First
- src/core/thinking_os/budget.py
- src/core/thinking_os/tools/cognition.py
- docs/adapters/claude-sdk.md
- src/core/thinking_os/tests/test_budget.py

## Repro Steps
Set `COS_DAILY_BUDGET_USD` just above today's spend, then call `cos_dispatch_parallel_run` with 3 formula_ids: the gate compares spent-only against the cap, passes, and `asyncio.gather` spawns all 3 concurrently; the cap is only observed after all 3 have landed their cost rows.

## Acceptance (G/W/T) — *this IS the Definition of Done*

- **Given** a configured cap whose remaining headroom is smaller than N dispatches, **When** `cos_dispatch_parallel_run` is called with N formula_ids, **Then** it returns `fail("budget", ...)` before any sub-agent is spawned.
- **Given** no dispatch-cost history in `formula_dispatches`, **When** the same call runs, **Then** the estimate is 0.0 and the gate behaves exactly as before (fail-open, never a spurious block).
- **Given** no cap configured (the default), **When** any dispatch runs, **Then** behaviour is unchanged.
- **Given** a single-role `cos_dispatch_formula_run`, **When** it runs, **Then** the gate stays spent-only — unchanged by design (one check authorizes one dispatch).
- **Given** a per-chain cap (`COS_CHAIN_BUDGET_USD`), **When** the fan-out would exceed it, **Then** `chain_check` blocks on the projected total.

## Work Log
- 2026-07-24 [claude]: Edit claude-sdk.md
- 2026-07-24 [claude]: Edit claude-sdk.md
- 2026-07-24 [claude]: Edit budget.py
- 2026-07-24 [claude]: Edit budget.py
- 2026-07-24 [claude]: Edit cognition.py
- 2026-07-24 [claude]: Edit test_budget.py
- 2026-07-24 [claude]: Edit test_dispatch_safety.py
- 2026-07-24 [claude]: Edit smoke_estimate.py
- 2026-07-24 [claude]: Edit budget.py
- 2026-07-24 [claude]: Edit test_dispatch_safety.py
- 2026-07-24 [claude]: Edit smoke_parallel_gate.py
- 2026-07-24 [claude]: Implemented + verified. budget.estimate_dispatch_cost (median of recent cost-bearing dispatches x count, window 20)…
- 2026-07-24 [claude]: committed 15b0d122 · 5 files
- 2026-07-24 [claude]: Status transitioned to complete via cos task-done.
