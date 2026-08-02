---
id: TASK-850
title: "Derive per-task reward label (derived_outcome) from the verify ledger, not agent self-report"
swimlane: core
kind: feature
epic: null
labels: [learning-loop, reward-signal, keep, ready]
status: complete
priority: P2
appetite: 1d
created: 2026-07-24
started: 2026-08-02
completed: 2026-08-02
agent_session: ses-claude-20260527-151803-0b9f
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
1. **Given** a completed task whose tree carries fresh verify-ledger verdicts (same git HEAD), **When** the outcome is recorded, **Then** derived_outcome is set from the ledger with derived_provenance=ledger.
2. **Given** a task with no ledger verdict for the current tree, **When** the outcome is recorded, **Then** derived_outcome falls back to the self-reported outcome with derived_provenance=self_report (never dropped).
3. **Given** existing metric_trend baselines, **When** the migration and recorder land, **Then** the original outcome column is unchanged (additive only).

## Rollback
Drop nothing: the columns are additive and readers ignore them; revert the recorder wiring commit to stop populating.

## Work Log
- 2026-08-02 [claude]: Edit task-lifecycle.md
- 2026-08-02 [claude]: Edit new-project.md
- 2026-08-02 [claude]: commit 92e22e3fca — feat(cli): --enable-module escape from profile+disable union on init/adopt
- 2026-08-02 [claude]: Edit database.py
- 2026-08-02 [claude]: Edit record_outcome.py
- 2026-08-02 [claude]: Edit record_outcome.py
- 2026-08-02 [claude]: commit 833fba5019 — feat(learning): derive per-task reward label from the verify ledger (v52)
- 2026-08-02 [claude]: Implemented v52 migration (derived_outcome + derived_provenance on task_outcomes) + ledger derivation in…
