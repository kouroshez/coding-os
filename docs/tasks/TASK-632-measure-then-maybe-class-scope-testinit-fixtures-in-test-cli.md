---
id: TASK-632
title: "Measure then (maybe) class-scope TestInit fixtures in test_cli.py"
swimlane: core
kind: chore
epic: null
labels: [ready]
status: complete
priority: P3
appetite: 1d
created: 2026-06-27
started: 2026-06-27
completed: 2026-06-27
agent_session: ses-claude-20260627-161919-30e5
depends_on: []
blocked_by: []
references: []
---
# TASK-632: Measure then (maybe) class-scope TestInit fixtures in test_cli.py

**Outcome (one sentence):** test_cli.py's heavy TestInit class runs `cos init` per test; IF profiling proves a class-scope fixture is both safe (the tests are read-only assertions on one init, not init variations) and a material wall-clock win, convert it — otherwise document why not. Decision is data-driven, not assumed.

## Work Log
- 2026-06-28 [claude]: MEASURED (pytest TestInit --durations=0): 19 tests, 35.83s total; per-init ~1.6-2.5s (slowest test_idempotent_init…
