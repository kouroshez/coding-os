---
id: TASK-670
title: "Class-scoped scaffold fixture for test-cli and test-adapters \u2014 kill the per-test cos-init cost"
swimlane: infra
kind: refactor
epic: test-discipline
labels: [tests, scaffold, perf, ready]
status: archive
priority: P2
appetite: 3d
created: 2026-06-30
started: 2026-07-01
completed: 2026-07-01
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-670: Class-scoped scaffold fixture for test-cli and test-adapters — kill the per-test cos-init cost

**Outcome (one sentence):** test-cli and test-adapters share a class-scoped scaffold fixture (mirroring test_template_scaffold's _class_scaffold) so cos init runs once per test CLASS instead of per test, cutting their wall-clock materially against the recorded baselines (test-cli ~762s, test-adapters ~153s) with zero change to assertions or isolation.

## Read First
- tests/test_cli.py
- tests/test_adapters.py
- tests/test_template_scaffold.py
- docs/engineering/test-governance.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the test-cli suite, **When** it runs with the class-scoped fixture, **Then** cos init executes once per test class (not per test) and every assertion still passes.
- **Given** the test-adapters suite, **When** it runs, **Then** the same class-scoped scaffold applies and wall-clock drops measurably versus the recorded baseline.
- **Given** test isolation requirements, **When** the fixture is shared within a class, **Then** no test leaks state into another, proven by a clean repeat run.

## Work Log
- 2026-07-01 [claude]: Class-scoped scaffold applied to the largest scaffold class in each suite: TestInit (15 read-only inits->1 via…
- 2026-07-01 [claude]: committed 3f22dab9 · 2 files
- 2026-07-01 [claude]: Status transitioned to complete via cos task-done.
