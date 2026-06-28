---
id: TASK-638
title: "Upgrade cos_route_model to a Thompson-sampling (Beta-Bernoulli) router over formula_dispatches"
swimlane: core
kind: feature
epic: multi-model-autonomy
labels: [routing, dispatch, bandit, ready]
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
# TASK-638: Upgrade cos_route_model to a Thompson-sampling (Beta-Bernoulli) router over formula_dispatches

**Outcome (one sentence):** cos_route_model gains a flag-gated Bayesian tier (COS_ROUTER_BANDIT): Thompson-sampling over per-model success/failure derived live from the formula_dispatches ledger (no separate state file to migrate), with an optional cost-tilt to prefer the cheaper tier when success rates tie. Cold-start (<COLD_START_THRESHOLD dispatches) delegates unchanged to today's frequentist/static router, so the flag-off default is byte-identical to current behaviour.

## Read First
- src/core/thinking_os/tools/routing.py
- src/core/thinking_os/tools/cognition.py
- docs/adapters/claude-sdk.md
- docs/governance/adr-role-dispatch-deferral.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** fewer than COLD_START_THRESHOLD dispatches, **When** route_model_bandit runs, **Then** it delegates to the existing route_model (zero cold behaviour change).
- **Given** >=N dispatches carrying model+status, **When** sampled, **Then** it returns a Thompson-sampled tier + confidence with alpha/beta derived from the ledger (Beta(1+success,1+failure)).
- **Given** COS_ROUTER_BANDIT unset (default), **When** dispatch resolves a model, **Then** behaviour is identical to today (precedence explicit>preset>role>empirical>default unchanged).
- **Given** a unit test on the Beta/Gamma sampler and the thinking_os matrix suite, **When** run, **Then** green.

## Work Log
- 2026-06-28 [claude]: Edit routing.py
- 2026-06-28 [claude]: Edit routing.py
- 2026-06-28 [claude]: Edit routing.py
- 2026-06-28 [claude]: Edit server.py
- 2026-06-28 [claude]: Edit server.py
- 2026-06-28 [claude]: Edit server.py
- 2026-06-28 [claude]: Edit test_routing.py
- 2026-06-28 [claude]: Edit test_routing.py
- 2026-06-28 [claude]: Edit commit638.txt
- 2026-06-28 [claude]: routing.py: added route_model_bandit (gated by COS_ROUTER_BANDIT) — Thompson-sampling Beta-Bernoulli over the SAME…
- 2026-06-28 [claude]: Status transitioned to complete via cos task-done.
