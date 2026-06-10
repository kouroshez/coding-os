---
id: TASK-334
title: "Fix pre-existing test failures: test_cli test_idempotent_init (assert 3==0) + 2 collection errors (test_intent_classifier, test_route_audits ImportError)"
swimlane: core
kind: bug
epic: null
labels: [test-governance, pre-existing, ready]
status: icebox
priority: P2
appetite: 1d
created: 2026-06-10
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-334: Fix pre-existing test failures: test_cli test_idempotent_init (assert 3==0) + 2 collection errors (test_intent_classifier, test_route_audits ImportError)

**Outcome (one sentence):** tests/test_cli.py::TestInit::test_idempotent_init passes; tests/test_intent_classifier.py and tests/test_route_audits.py collect cleanly under the default extras.

## Read First
- docs/engineering/test-governance.md
- tests/test_intent_classifier.py
- tests/test_cli.py

## Repro Steps
1. (fill in: exact steps to reproduce)
2. ...
Expected: ...
Actual: ...

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the matrix command for test-cli and a bare collect of tests/
- **When** run on a clean tree
- **Then** test_idempotent_init passes and collection reports 0 errors

## Work Log
