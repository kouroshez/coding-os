---
id: TASK-622
title: "Codify test cadence + run_in_background rule (F1) and docs-lint close-only (F4)"
swimlane: docs
kind: chore
epic: null
labels: [governance, ready]
status: archive
priority: P2
appetite: 2h
created: 2026-06-27
started: 2026-06-27
completed: 2026-06-27
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-622: Codify test cadence + run_in_background rule (F1) and docs-lint close-only (F4)

**Outcome (one sentence):** A fresh agent session reads, in test-discipline.md, an explicit "Test cadence" policy that fixes the idle-wait + over-testing pain: (1) targeted single test during dev, (2) matrix suite ONCE at task close, (3) heavy suites (>~60s) launched with Bash run_in_background — keep working, never idle-wait, with the test-governor run-lock caveat, (4) docs-lint at close only (work-log churn in docs/tasks/ is already digest-excluded). AGENTS.md Core Loop references backgrounding heavy suites / never idle-wait. Doc-only, zero code blast radius. Derived from the 2026-06-27 6-agent audit (F1+F4, the only red-team-verified zero-risk fixes).

## Work Log
- 2026-06-27 [claude]: Edit test-discipline.md
- 2026-06-27 [claude]: Scope decision: delivered the test-discipline.md "Test cadence" section (F1+F4). test-discipline.md is an…
- 2026-06-27 [claude]: Status transitioned to complete via cos task-done.
