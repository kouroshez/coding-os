---
id: TASK-1125
title: "chore(tests): delete dead and prose-only tests and dedupe copied test helpers"
swimlane: infra
kind: chore
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-11-24
started: 2026-11-24
completed: 2026-11-24
agent_session: ses-claude-20261123-135444-89e7
depends_on: []
blocked_by: []
references: []
---
# TASK-1125: chore(tests): delete dead and prose-only tests and dedupe copied test helpers

**Outcome (one sentence):** The dead, prose-only and duplicate tests the audit proved are gone and the 9x inherited PR test runs once. (Amended 2026-11-24: the v40/v49/v50 migration tests stay, since those migrations still run on an upgrading database; merging the copied run_hook/_resolve_cos_var/_class_scaffold helpers was dropped, because it changes no test's cost or coverage.)

## Read First
- tests/test_hooks_blocks.py
- tests/_cli_suite/pr_base.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the audit list, **When** the suite is collected, **Then** none of the listed tests exist and every remaining test still passes.
- **Given** test_submit_circuit_breaker_caps_open_prs, **When** collected, **Then** it runs once.

## Work Log
- 2026-11-24 [claude]: commit f1bb170168 — test: delete 12 dead or prose-only tests and stop running one PR test 9 times
- 2026-11-24 [claude]: commit 187ea7fa1f — test(db): keep the v40/v49/v50 migration tests; those migrations still run on upgrade
- 2026-11-24 [claude]: Status transitioned to complete via cos task-done.
