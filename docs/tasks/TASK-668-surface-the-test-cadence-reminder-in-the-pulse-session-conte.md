---
id: TASK-668
title: "Surface the test-cadence reminder in the pulse/session-context block (additive to the TASK-622 doc)"
swimlane: core
kind: chore
epic: test-discipline
labels: [tests, cadence, pulse, ready]
status: complete
priority: P3
appetite: 1d
created: 2026-06-30
started: 2026-07-01
completed: 2026-07-01
agent_session: ses-claude-20260630-011740-9a32
depends_on: []
blocked_by: []
references: []
---
# TASK-668: Surface the test-cadence reminder in the pulse/session-context block (additive to the TASK-622 doc)

**Outcome (one sentence):** The agent-only pulse block emitted by session-context carries a concise test-cadence reminder (targeted-test during dev, matrix-suite once at close, background heavy suites, never idle-wait) so the TASK-622 policy is seen in-band rather than only in test-discipline.md, which agents skip — additive, no new enforcement, banner contract unchanged.

## Work Log
- 2026-07-01 [claude]: session-context appends a one-line [test-cadence] reminder to the agent-only pulse on formal-work modes (suppressed…
- 2026-07-01 [claude]: committed b7b50365 · 3 files
- 2026-07-01 [claude]: Status transitioned to complete via cos task-done.
