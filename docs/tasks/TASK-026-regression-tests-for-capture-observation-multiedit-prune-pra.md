---
id: TASK-026
title: "regression tests for capture-observation MultiEdit + prune PRAGMA fixes"
swimlane: core
kind: test
epic: null
labels: [regression]
status: archive
priority: P1
appetite: "1h"
created: 2026-05-23
started: 2026-05-23
completed: 2026-05-23
agent_session: ses-claude-20260523-010526-e647
depends_on: []
blocked_by: []
references:
  - src/core/hooks/capture-observation.sh
  - src/scripts/prune_deleted_path.py
---
# TASK-026: regression tests for the two silent-revert risks

**Outcome (one sentence):** Both TASK-016 (MultiEdit shell filter) and TASK-017 (PRAGMA foreign_keys = ON) get pytest coverage so a future ruff format, refactor, or copy-paste cannot silently revert the fix without a red test.

## Read First
- [tests/test_hooks_phase_f_memory.py](../../tests/test_hooks_phase_f_memory.py) — pattern for shell-hook tests (`_invoke` helper, env scoping)
- [src/core/hooks/capture-observation.sh](../../src/core/hooks/capture-observation.sh) — TASK-016 fix at line 28
- [src/scripts/prune_deleted_path.py](../../src/scripts/prune_deleted_path.py) — TASK-017 fix at line 38

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the two regressions land
- **When** a future change removes `MultiEdit` from the shell case OR drops `PRAGMA foreign_keys = ON` from the prune script
- **Then** the pytest suite flips red with a clear message naming the regression; `make verify-hooks` + targeted pytest stay green on the current code; tests are fast (<1 s combined) and self-contained (tmp_path fixtures, no real DB).

## Work Log
- 2026-05-23 — added `tests/test_capture_and_prune_regressions.py` with 8 tests across 2 classes (5 for capture-observation MultiEdit, 3 for prune_deleted_path PRAGMA). Each test pins both source-level invariant (string-grep on the fix line) AND runtime behavior (subprocess spawn + DB fixture). 8 passed in 0.23s. `ruff format` + `ruff check` clean. Self-contained — no real DB, tmp_path fixtures only.
- 2026-05-23 [claude]: Status transitioned to complete via cos task-done.
