---
id: TASK-674
title: "Spike \u2014 evaluate pytest-testmon per-test selection behind an opt-in flag vs the no-xdist simplicity stance"
swimlane: infra
kind: spike
epic: test-discipline
labels: [tests, testmon, ready]
status: archive
priority: P3
appetite: 1d
created: 2026-06-30
started: 2026-07-01
completed: 2026-07-01
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-674: Spike — evaluate pytest-testmon per-test selection behind an opt-in flag vs the no-xdist simplicity stance

**Outcome (one sentence):** A time-boxed decision doc evaluates pytest-testmon per-test selection behind an opt-in COS_TESTMON flag against the deliberately-simple no-xdist stance (TASK-331): measured redundant-run reduction on at least the thinking_os and cli suites vs the added dependency and complexity, ending in a keep-or-defer recommendation — code ships only if the spike says keep.

## Work Log
- 2026-07-01 [claude]: Spike measured testmon (run2 unchanged tree: 56 deselected, 0.06s) — works, but the win is redundant with the…
- 2026-07-01 [claude]: committed e7c6dba9 · 1 file
- 2026-07-01 [claude]: Status transitioned to complete via cos task-done.
