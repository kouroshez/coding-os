---
id: TASK-789
title: "test(scheduled): smoke-test cos-nightly entrypoint runs as a direct script (Rule 26 dogfood)"
swimlane: core
kind: test
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-07-05
started: 2026-07-04
completed: 2026-07-04
agent_session: ses-claude-20260704-201536-1b8d
depends_on: []
blocked_by: []
references: []
---
# TASK-789: test(scheduled): smoke-test cos-nightly entrypoint runs as a direct script (Rule 26 dogfood)

**Outcome (one sentence):** A subprocess smoke test in src/core/scheduled/tests/test_nightly.py runs `python nightly.py --help` as a real child process and asserts exit 0 + usage output — reproducing the exact path (`python3 src/core/scheduled/nightly.py`) that crashed with ModuleNotFoundError before the sys.path bootstrap fix. The in-process TestNightlyMain tests cannot catch this class because pytest already has the package on sys.path; only a subprocess of the file exercises the bootstrap. Machine-checks Critical Rule 26 for this entrypoint.

## Read First
- src/core/scheduled/nightly.py
- src/core/scheduled/tests/test_nightly.py
- src/core/rules/test-discipline.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** nightly.py's sys.path bootstrap regresses (a path dropped from the _SRC/_CORE/_THINKING_OS insert)
- **When** the test-scheduled suite runs test_script_runs_as_direct_subprocess
- **Then** the child `python nightly.py --help` exits non-zero and the test FAILS — catching the ModuleNotFoundError class the in-process main() tests miss; with the bootstrap intact it exits 0 with the usage string and PASSES, adding under 2s and not slow-marked.

## Work Log
- 2026-07-05 [claude]: Edit nightly.py
- 2026-07-05 [claude]: Edit test_nightly.py
- 2026-07-05 [claude]: Edit mutation_proof.py
- 2026-07-05 [claude]: commit 9ee046f5df — test(scheduled): smoke-test cos-nightly entrypoint runs as a direct script
- 2026-07-05 [claude]: Smoke test added + committed (9ee046f5): TestNightlyEntrypointSmoke runs `python nightly.py --help` via subprocess,…
- 2026-07-05 [claude]: Edit test_nightly.py
- 2026-07-05 [claude]: commit 5fcf70e75e — fix(test): -S in nightly smoke test so the editable finder can't mask a broken bootstrap
- 2026-07-05 [claude]: False-green fixed + committed (5fcf70e7): added -S to the subprocess so the editable-install finder can't resolve…
