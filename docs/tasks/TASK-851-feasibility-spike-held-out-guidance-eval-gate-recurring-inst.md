---
id: TASK-851
title: "Feasibility spike: held-out guidance-eval gate (recurring-instance volume vs rollout variance)"
swimlane: core
kind: spike
epic: null
labels: [learning-loop, eval-gate, feasibility, keep]
status: icebox
priority: P2
appetite: 1d
created: 2026-07-24
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-851: Feasibility spike: held-out guidance-eval gate (recurring-instance volume vs rollout variance)

**Outcome (one sentence):** Measure whether coding-os's real task stream has enough recurring, checkable instances to form a held-out set with signal above stochastic-rollout variance, under a per-night cost_usd ceiling, BEFORE building the L-effort eval leg. Probes include input_slice persistence and recurring-task clustering. Output: go/no-go for the eval build with measured signal-vs-noise. See ADR-0016.

## Work Log
- 2026-08-02 [claude]: Triage 2026-08-02: deliberately staying keep — this spike measures recurring-instance volume vs rollout variance over…
- 2026-08-03 [claude]: Readiness trigger (measured 2026-08-03): the spike's input is derived_outcome-labeled outcomes (TASK-850, complete) —…
