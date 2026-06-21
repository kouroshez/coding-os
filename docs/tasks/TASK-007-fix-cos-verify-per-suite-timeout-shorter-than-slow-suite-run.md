---
id: TASK-007
title: "Fix cos verify per-suite timeout shorter than slow suite runtime"
swimlane: cli
kind: bug
epic: null
labels: [verify, tooling]
status: archive
priority: P2
appetite: "1d"
created: 2026-05-21
started: null
completed: 2026-05-21
agent_session: ses-claude-20260521-183248-4524
depends_on: []
blocked_by: []
references: []
---
# TASK-007: Fix cos verify per-suite timeout shorter than slow suite runtime

**Outcome (one sentence):** cos verify completes test_template_scaffold (551s) without TimeoutExpired — per-suite subprocess timeout is large enough or configurable.

## Read First
- src/cli/verify_since_edit.py

## Repro Steps
1. Touch a file that maps to the `test_template_scaffold` suite (e.g. a doc under `src/templates/_base/scaffold/`).
2. Run `cos verify`.
3. The suite runs ~551s; `_run_suite` in `verify_since_edit.py` calls `subprocess.run(..., timeout=300)`.
Expected: `cos verify` runs the suite to completion and reports pass/fail.
Actual: `subprocess.TimeoutExpired` is raised at 300s and propagates unhandled through `fut.result()`, crashing `cos verify` with a traceback.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a changed file whose matrix suite runs longer than 300s (e.g. `test_template_scaffold`, ~551s).
- **When** `cos verify` runs that suite.
- **Then** the per-suite timeout is large enough to let the suite finish, and a genuine timeout is caught and reported as a failed `SuiteResult` (no unhandled `TimeoutExpired` traceback).

## Work Log
- 2026-05-21 [claude]: Status transitioned to complete via cos task-done.
