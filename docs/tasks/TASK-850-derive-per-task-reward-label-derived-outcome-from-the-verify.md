---
id: TASK-850
title: "Derive per-task reward label (derived_outcome) from the verify ledger, not agent self-report"
swimlane: core
kind: feature
epic: null
labels: [learning-loop, reward-signal, keep]
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

# TASK-850: Derive per-task reward label (derived_outcome) from the verify ledger, not agent self-report

**Outcome (one sentence):** task_outcomes/agent_metrics gain an ADDITIVE derived_outcome column sourced from the tree-keyed verify ledger (.last-verify.json) PASS/FAIL, with a provenance flag and a self-report fallback where ledger coverage is absent — so the learning loop and any future eval gate optimize a signal the agent cannot self-report. Strongest single bet: ships value independently. See ADR-0016.

## Read First
- docs/architecture/adr/0016-gated-skill-evolution-roadmap-extend-not-build.md
- src/core/thinking_os/tools/metrics.py
- src/core/board_os/verify_suites.py
- docs/governance/task-lifecycle.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
Given a completed task whose changed files matched a verify-suites glob and the ledger recorded PASS/FAIL for that tree, When outcome is recorded, Then derived_outcome is set from the ledger with provenance=ledger. Given a task with no ledger verdict, Then derived_outcome falls back to self-report with provenance=self_report (never dropped). Given existing metric_trend baselines, Then the original outcome column is unchanged (additive only).

## Work Log
