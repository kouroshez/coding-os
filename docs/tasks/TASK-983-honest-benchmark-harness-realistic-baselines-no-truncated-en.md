---
id: TASK-983
title: "Honest benchmark harness \u2014 realistic baselines, no truncated envelopes, net of context tax"
swimlane: infra
kind: feature
epic: honest-benchmarks
labels: [ready]
status: icebox
priority: P1
appetite: 1d
created: 2026-08-15
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-983: Honest benchmark harness — realistic baselines, no truncated envelopes, net of context tax

**Outcome (one sentence):** The published harness can no longer produce a flattering number by accident: it defaults to the baseline a competent agent actually runs, refuses to score a truncated envelope, and reports the break-even query count that includes the always-on context cost.

## Read First
- src/core/graph_os/bench/third_party.py
- src/core/graph_os/bench/token_cost.py
- docs/engineering/third-party-token-bench.md

## Acceptance (G/W/T) — *this IS the Definition of Done*

- **Given** the third-party harness, **When** it runs without flags, **Then** it scores against the competent-agent baseline (grep output plus bounded reads of the top matching files), and the read-everything baseline is available but opt-in.
- **Given** a probe whose envelope reports walk_truncated or result_truncated, **When** the harness scores it, **Then** it widens the budget until the envelope is complete, or records the probe as incomplete — never scores a truncated answer as a saving.
- **Given** a measured run, **When** the report is emitted, **Then** it includes the always-on context cost and the break-even number of structural queries at which the graph repays it.
- **Given** the published methodology doc, **When** the harness changes, **Then** the doc and its results table are regenerated in the same commit.

## Work Log
