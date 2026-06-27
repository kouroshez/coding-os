---
id: TASK-632
title: "Measure then (maybe) class-scope TestInit fixtures in test_cli.py"
swimlane: core
kind: chore
epic: null
labels: [ready]
status: icebox
priority: P3
appetite: 1d
created: 2026-06-27
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-632: Measure then (maybe) class-scope TestInit fixtures in test_cli.py

**Outcome (one sentence):** test_cli.py's heavy TestInit class runs `cos init` per test; IF profiling proves a class-scope fixture is both safe (the tests are read-only assertions on one init, not init variations) and a material wall-clock win, convert it — otherwise document why not. Decision is data-driven, not assumed.

## Work Log
