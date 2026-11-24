---
id: TASK-1104
title: "fix(board): the test-modules verify suite names test classes that exist"
swimlane: "board_os"
kind: bug
epic: null
labels: [hooks, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-11-24
started: 2026-11-23
completed: 2026-11-23
agent_session: ses-claude-20261123-135444-89e7
depends_on: []
blocked_by: []
references: []
---
# TASK-1104: fix(board): the test-modules verify suite names test classes that exist

**Outcome (one sentence):** Editing registry.yaml or subsystems.yaml asks for a test-modules command that runs, so task-done can be satisfied without an override.

## Read First
- src/core/board_os/verify-suites.yaml
- tests/test_cli.py

## Repro Steps
verify-suites.yaml test-modules runs tests/test_cli.py::TestSubsystems, a class split into TestSubsystemsRegistry/Drift/InitFlags; pytest exits 4 "no match", so the suite can never pass and every registry edit blocks task-done.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a change to src/core/hooks/registry.yaml, **When** enforce-verify names the test-modules command, **Then** running that command collects and runs the subsystem tests instead of exiting 4 with "not found".

## Work Log
- 2026-11-24 [claude]: verify-suites.yaml test-modules named tests/test_cli.py::TestSubsystems, a class split into…
- 2026-11-24 [claude]: Status transitioned to complete via cos task-done.
