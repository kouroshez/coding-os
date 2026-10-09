---
id: TASK-1057
title: "Gate the scaffold suites that still run only in the nightly slow job"
swimlane: infra
kind: chore
epic: null
labels: [parked]
status: icebox
priority: P2
appetite: 1d
created: 2026-10-07
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-1057: Gate the scaffold suites that still run only in the nightly slow job

**Outcome (one sentence):** the slow tests that run only nightly (the `test_template_scaffold_*` suites, add/remove-stack, cli init/setup/update/materialize, the phase-F hook suites, the wheel builds, the RAG pipeline smoke) gate pull requests or carry a recorded reason why one cannot, so RISK-004 can close.

## Work Log
