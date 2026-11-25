---
id: TASK-1124
title: "perf(tests): stop test inits from loading the embedding model and rebuilding scaffolds per test"
swimlane: infra
kind: chore
epic: null
labels: [ready]
status: complete
priority: P1
appetite: 1d
created: 2026-11-24
started: 2026-11-24
completed: 2026-11-24
agent_session: ses-claude-20261123-135444-89e7
depends_on: []
blocked_by: []
references: []
---
# TASK-1124: perf(tests): stop test inits from loading the embedding model and rebuilding scaffolds per test

**Outcome (one sentence):** No test run starts the embedding model from a `cos init` (in process, as a subprocess, or in a class/module fixture), with no loss of assertion coverage. (Amended 2026-11-24: the shared scaffold builds in the scaffold suites were already class- or module-scoped; the 13 per-test rebuilds left in test_cli now cost about 3 s each without indexing and were not worth the risk of a fixture rewrite.)

## Read First
- tests/conftest.py
- tests/test_cli.py
- src/cli/_init_indexing.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** any test that runs cos init, **When** it runs, **Then** no indexing subprocess starts unless the test is about indexing.
- **Given** COS_INIT_SKIP_INDEX=1, **When** either init indexer runs, **Then** it starts no subprocess (tests/test_init_graph_index.py).

## Work Log
- 2026-11-24 [claude]: commit aab84bb79b — perf(tests): no test init loads the embedding model, in process or as a subprocess
- 2026-11-24 [claude]: commit 8d01971953 — perf(tests): set the index opt-out at pytest start so class and module scaffolds see it
- 2026-11-24 [claude]: commit b2295bc869 — test(init): prove the index opt-out starts no subprocess; drop the stubs it replaces
- 2026-11-24 [claude]: Status transitioned to complete via cos task-done.
