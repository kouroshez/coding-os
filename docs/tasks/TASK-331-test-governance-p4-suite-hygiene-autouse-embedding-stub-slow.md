---
id: TASK-331
title: "Test-governance P4: suite hygiene \u2014 autouse embedding stub, slow markers, -m 'not slow' matrix default, make test-slow"
swimlane: core
kind: test
epic: test-governance
labels: [test-governance, performance, ready]
status: archive
priority: P1
appetite: 1d
created: 2026-06-10
started: 2026-06-09
completed: 2026-06-10
agent_session: ses-claude-20260527-151803-0b9f
depends_on: [TASK-327]
blocked_by: []
references: []
---
# TASK-331: Test-governance P4: suite hygiene — autouse embedding stub, slow markers, -m 'not slow' matrix default, make test-slow

**Outcome (one sentence):** thinking_os suite wall-clock >=30% below P0 baseline via autouse embedding stub (COS_TEST_REAL_EMBEDDINGS=1 escape hatch, unify the 7 existing mock sites) + slow markers on scaffold/install.sh/uv-run-spawning tests; matrix commands exclude slow; make test-slow covers the rest; NO pytest-xdist.

## Read First
- docs/engineering/test-governance.md
- src/core/thinking_os/tests/conftest.py
- tests/conftest.py
- src/core/thinking_os/embeddings.py
- src/core/rules/test-discipline.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the default matrix command per suite
- **When** executed after the change
- **Then** slow tests are deselected, wall-clock >=30% lower than P0 baseline (report actual), COS_TEST_REAL_EMBEDDINGS=1 restores the real path, make test-slow runs the slow set, all matrix suites green

## Work Log
- 2026-06-10 [claude]: Status transitioned to complete via cos task-done.
