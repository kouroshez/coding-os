---
id: TASK-987
title: "Hook subprocess timeout of 5s flakes on cold CI runners and reddens main"
swimlane: infra
kind: bug
epic: honest-benchmarks
labels: [ready]
status: in_progress
priority: P1
appetite: 1d
created: 2026-08-15
started: 2026-08-15
completed: null
agent_session: ses-claude-20260814-120316-413b
depends_on: []
blocked_by: []
references: []
---
# TASK-987: Hook subprocess timeout of 5s flakes on cold CI runners and reddens main

**Outcome (one sentence):** A hang-detector timeout stops doubling as a performance assertion, so a cold or loaded runner cannot turn main red for a hook that finishes in under a tenth of a second.

## Read First
- tests/test_capture_and_prune_regressions.py
- tests/test_script_entrypoints.py
- src/core/hooks/capture-observation.sh

## Repro Steps
Nightly CI run 31871857926 on c23c2777: `tests/test_capture_and_prune_regressions.py::TestCaptureObservationMultiEdit::test_filter_accepts_multiedit` failed with `subprocess.TimeoutExpired` after 5 seconds on macos-latest py3.12. The same commit passed the same job hours earlier. Locally the hook completes in 0.09s across three runs, so 5s is ~55x the real cost and is exceeded only by runner cold start and contention.

## Acceptance (G/W/T) — *this IS the Definition of Done*

- **Given** a subprocess timeout in a hook regression test, **When** it is set, **Then** it is sized as a hang detector rather than a performance budget, and the constant says so.
- **Given** the suite, **When** it runs locally, **Then** it still passes and the real hook runtime is unchanged.
- **Given** the nightly macOS job, **When** it next runs, **Then** this test is not the reason main is red.

## Work Log
- 2026-08-15 [claude]: Edit test_capture_and_prune_regressions.py
- 2026-08-15 [claude]: Named the constant SUBPROCESS_TIMEOUT_S = 30 (matching SMOKE_TIMEOUT_S in test_script_entrypoints.py) and replaced…
