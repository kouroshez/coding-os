---
id: TASK-960
title: "Freeze the clock in the reconcile determinism test so a second boundary cannot fail CI"
swimlane: core
kind: bug
epic: null
labels: [ready]
status: complete
priority: P1
appetite: 1d
created: 2026-08-13
started: 2026-08-12
completed: 2026-08-12
agent_session: ses-claude-20260807-224955-abc1
depends_on: []
blocked_by: []
references: []
---
# TASK-960: Freeze the clock in the reconcile determinism test so a second boundary cannot fail CI

**Outcome (one sentence):** test_reconcile_is_read_only compares two reconcile envelopes under a frozen clock, so it fails only on real nondeterminism and never on a wall-clock tick.

## Read First
- src/core/board_os/tests/test_mcp_archive_tools_reconcile.py
- src/core/board_os/_mcp_cards.py

## Repro Steps
CI run 31660267142 (head f5abf2fb, docs-only diff): 1 failed, 3483 passed. `AssertionError: reconcile must be deterministic/idempotent`, diff is exactly `nds": 28801` vs `nds": 28800` — status_dwell_seconds, computed from time.time() in _mcp_cards.py:42, differing by one second between the two calls.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** two cos_task_reconcile calls that straddle a one-second boundary
  **When** test_reconcile_is_read_only runs
  **Then** it passes, because the compared envelopes no longer carry a live clock reading.

- **Given** a reconcile implementation made genuinely nondeterministic
  **When** the same test runs
  **Then** it still fails — the assertion keeps its teeth.

## Work Log
- 2026-08-13 [claude]: Edit test_mcp_archive_tools_reconcile.py
- 2026-08-13 [claude]: Edit test_mcp_archive_tools_reconcile.py
- 2026-08-13 [claude]: clock frozen for the compared calls; advancing-clock repro fails, injected nondeterminism still fails, fix passes;…
- 2026-08-13 [claude]: commit 461598285c — fix(board_os): freeze the clock in the reconcile determinism test
- 2026-08-13 [claude]: Status transitioned to complete via cos task-done.
