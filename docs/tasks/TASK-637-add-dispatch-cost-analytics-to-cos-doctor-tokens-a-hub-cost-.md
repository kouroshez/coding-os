---
id: TASK-637
title: "Add dispatch cost analytics to cos doctor --tokens + a Hub cost/health route (MAD anomaly, burn-rate, budget ladder)"
swimlane: core
kind: feature
epic: cognitive-kernel-hardening
labels: [cost, observability, doctor, hub, ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-28
started: 2026-06-28
completed: 2026-06-28
agent_session: ses-claude-20260627-204916-f0ee
depends_on: []
blocked_by: []
references: []
---
# TASK-637: Add dispatch cost analytics to cos doctor --tokens + a Hub cost/health route (MAD anomaly, burn-rate, budget ladder)

**Outcome (one sentence):** Surface cost GAUGES over the existing formula_dispatches ledger (we already have the budget GATE): median+MAD anomaly flag on per-session spend, window-over-window burn-rate acceleration, a 50/75/90/100% budget-utilization ladder, and a Hub /cognition/cost/health route — all in-process Python over data we already store, no new subsystem, no Prometheus, no counterfactual baselines.

## Read First
- src/cli/doctor_tokens.py
- src/core/thinking_os/budget.py
- src/core/web/routes/cognition.py
- src/core/thinking_os/database.py

## Implementation Notes (verified against source 2026-06-28)
formula_dispatches timestamp column is `ts` (NOT created_at); cost columns cost_usd/budget_usd added in migration v23. LATENT BUG to fix in the same change: budget.py `_spent_today` queries `WHERE date(created_at) = ?` against formula_dispatches, which has no created_at column, so it silently returns 0.0 (try/except sqlite3.OperationalError) and the daily budget gate never sees today's spend. Standardize on `date(ts)` (the working /cost route already uses ts).

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** >=3 sessions of formula_dispatches.cost_usd, **When** cos doctor --tokens runs, **Then** it flags any session beyond modified-z 3.5 (median+MAD, n>=3 guard).
- **Given** 14 days of dispatch spend, **When** analyzed, **Then** it reports latest-day vs prior-mean delta_pct and an accelerating flag (today's partial day labelled).
- **Given** a daily budget cap, **When** utilization crosses 50/75/90/100%, **Then** the level (ok/info/warning/critical/hard_stop) is reported as a gauge; the existing fail-closed budget gate is unchanged.
- **Given** budget.py spent-today currently queries date(created_at) on a table that only has ts, **When** this ships, **Then** it is corrected to date(ts) so the daily gate actually sees today's spend.
- **Given** GET /api/p/<slug>/cognition/cost/health, **When** called, **Then** it returns {anomaly,burn,budget,overall_ok} via the existing ok/fail envelope and fails open when no DB exists.
- **Given** the cli and thinking_os suites, **When** run, **Then** green.

## Work Log
- 2026-06-28 [claude]: Edit budget.py
- 2026-06-28 [claude]: Edit budget.py
- 2026-06-28 [claude]: Edit budget.py
- 2026-06-28 [claude]: Edit budget.py
- 2026-06-28 [claude]: Edit budget.py
- 2026-06-28 [claude]: Edit budget.py
- 2026-06-28 [claude]: Edit doctor_tokens.py
- 2026-06-28 [claude]: Edit doctor_tokens.py
- 2026-06-28 [claude]: Edit doctor.py
- 2026-06-28 [claude]: Edit cognition.py
- 2026-06-28 [claude]: Edit budget.py
- 2026-06-28 [claude]: Edit test_budget.py
- 2026-06-28 [claude]: Edit test_cognition_routes.py
- 2026-06-28 [claude]: Edit test_cognition_routes.py
- 2026-06-28 [claude]: Edit commit637.txt
- 2026-06-28 [claude]: Shipped cost gauges over formula_dispatches (all in-process, no new subsystem). budget.py: fixed _spent_today…
- 2026-06-28 [claude]: Status transitioned to complete via cos task-done.
