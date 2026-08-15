---
id: TASK-984
title: "Ablation eval harness \u2014 locked task set and pre-registered metrics for the four arms"
swimlane: infra
kind: feature
epic: honest-benchmarks
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-08-15
started: 2026-08-15
completed: 2026-08-15
agent_session: ses-claude-20260814-120316-413b
depends_on: []
blocked_by: []
references: []
---
# TASK-984: Ablation eval harness — locked task set and pre-registered metrics for the four arms

**Outcome (one sentence):** The open question "does this improve output quality, not just token count" becomes answerable — a locked task set drawn from this repo's own closed tasks, four arms, and metrics registered before any run so the result cannot be chosen after the fact.

## Read First
- docs/engineering/third-party-token-bench.md
- src/cli/doctor_tokens.py
- docs/governance/task-lifecycle.md

## Acceptance (G/W/T) — *this IS the Definition of Done*

- **Given** this repo's closed tasks, **When** the task-set builder runs, **Then** it emits a locked, versioned set of tasks that each carry a machine-checkable acceptance criterion and a known-good commit.
- **Given** the four arms (raw, graph-only, rules-only, full), **When** the harness is configured, **Then** each arm differs only in the instruction and retrieval layer, with model and seed held constant.
- **Given** the metric set, **When** it is defined, **Then** it is committed before any arm is executed, and includes completion rate, tokens per task, weighted cost per task, wall-clock, and the two ratios quality-per-dollar and completions-per-million-tokens.
- **Given** the harness, **When** this task closes, **Then** the deliverable is the runnable harness plus the registered protocol; no result is published that has not been executed.

## Work Log
- 2026-08-15 [claude]: Edit eval_taskset.py
- 2026-08-15 [claude]: Edit eval_taskset.py
- 2026-08-15 [claude]: Edit eval_taskset.py
- 2026-08-15 [claude]: Edit eval_taskset.py
- 2026-08-15 [claude]: Edit eval_taskset.py
- 2026-08-15 [claude]: Edit eval_taskset.py
- 2026-08-15 [claude]: Edit eval_taskset.py
- 2026-08-15 [claude]: Edit ablation-protocol.md
- 2026-08-15 [claude]: Pre-registered the ablation in docs/engineering/ablation-protocol.md — four arms differing only in the…
- 2026-08-15 [claude]: Status transitioned to complete via cos task-done.
