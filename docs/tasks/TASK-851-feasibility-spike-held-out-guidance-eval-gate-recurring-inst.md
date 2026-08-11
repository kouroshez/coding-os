---
id: TASK-851
title: "Feasibility spike: held-out guidance-eval gate (recurring-instance volume vs rollout variance)"
swimlane: core
kind: spike
epic: null
labels: [learning-loop, eval-gate, feasibility, keep, ready]
status: complete
priority: P2
appetite: 1d
created: 2026-07-24
started: 2026-08-11
completed: 2026-08-11
agent_session: ses-claude-20260807-224955-abc1
depends_on: []
blocked_by: []
references: []
---
# TASK-851: Feasibility spike: held-out guidance-eval gate (recurring-instance volume vs rollout variance)

**Outcome (one sentence):** Measure whether coding-os's real task stream has enough recurring, checkable instances to form a held-out set with signal above stochastic-rollout variance. Verdict: **NO-GO**, measured 2026-08-11.

## Read First
- [ADR-0016 § Spike verdict](../architecture/adr/0016-gated-skill-evolution-roadmap-extend-not-build.md) — the durable record and the re-open trigger

## Repro Steps
Query `task_outcomes` on the dogfood DB and group labeled rows by (domain, complexity, type); compare each cluster's binomial SE against the headroom above the current success rate.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the `derived_outcome`-labeled outcome stream from TASK-850
- **When** recurring-instance volume is measured against rollout variance
- **Then** a go/no-go verdict with the measured signal-vs-noise numbers is recorded in ADR-0016.

## Work Log
- 2026-08-02 [claude]: Triage 2026-08-02: deliberately staying keep — this spike measures recurring-instance volume vs rollout variance over…
- 2026-08-03 [claude]: Readiness trigger (measured 2026-08-03): the spike's input is derived_outcome-labeled outcomes (TASK-850, complete) —…
- 2026-08-11 [claude]: Edit 0016-gated-skill-evolution-roadmap-extend-not-build.md
- 2026-08-11 [claude]: commit b9326b0ee8 — docs(adr-0016): record the held-out eval-gate spike verdict as a measured no-go
- 2026-08-11 [claude]: Status transitioned to complete via cos task-done.
- 2026-08-11 [claude]: commit 011d778784 — chore(board): close the ten icebox cards worked this session
