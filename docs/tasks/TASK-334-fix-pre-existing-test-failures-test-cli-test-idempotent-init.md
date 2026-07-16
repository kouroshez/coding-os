---
id: TASK-334
title: "Fix pre-existing test failures: test_cli test_idempotent_init (assert 3==0) + 2 collection errors (test_intent_classifier, test_route_audits ImportError)"
swimlane: core
kind: bug
epic: null
labels: [test-governance, pre-existing, ready]
status: archive
priority: P2
appetite: 1d
created: 2026-06-10
started: 2026-06-10
completed: 2026-06-10
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-334: Fix pre-existing test failures: test_cli test_idempotent_init (assert 3==0) + 2 collection errors (test_intent_classifier, test_route_audits ImportError)

## Outcome
tests/test_cli.py::TestInit::test_idempotent_init passes; tests/test_intent_classifier.py and tests/test_route_audits.py collect cleanly under the default extras.

## Read First
- docs/engineering/test-governance.md
- tests/test_intent_classifier.py
- tests/test_cli.py

## Repro Steps
1. `uv run pytest tests/ -q --collect-only` → 2 errors: ModuleNotFoundError `extract_intent` and `web.routes.audits`.
2. Root cause: both production modules were deliberately deleted (2a43a661 dropped extract_intent helper; 0f386e9b removed the Audits page) but their test files were left behind — orphan tests, not import-path drift.
3. `test_idempotent_init` (assert 3 == 0 in the 2026-06-09 baseline) passes in isolation — transient: the concurrent session was mid-editing cli/board_os files while the baseline ran `cos init` from the live tree.
Expected: zero collection errors; test green.
Actual (pre-fix): 2 collection errors interrupted full collection.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the matrix command for test-cli and a bare collect of tests/
- **When** run on a clean tree
- **Then** test_idempotent_init passes and collection reports 0 errors

## Work Log
- 2026-06-10 removed orphan tests (git rm), fixed conftest comment, doc note in test-governance.md. Verified: tests/ collects 2,586 / 0 errors; test_idempotent_init 1 passed in 58s isolated. Committed on main.
- 2026-06-10 [claude]: Status transitioned to complete via cos task-done.
